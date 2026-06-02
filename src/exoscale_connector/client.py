"""The low-level HTTP client for the Exoscale APIv2.

:class:`ExoscaleClient` owns a signed ``requests`` session and exposes verb
helpers plus asynchronous-operation polling. Resource classes
(:mod:`exoscale_connector.resources`) sit on top of it and add typed, per-asset
behaviour — application code normally uses those rather than this client directly.
"""
from __future__ import annotations

import time
from typing import Any, Optional, Union

import requests

from .auth import ExoscaleV2Auth
from .config import ClientConfig
from .errors import APIError, NotFoundError, OperationError, OperationTimeoutError
from .models import Operation

# HTTP statuses that are safe to retry with backoff (transient server / rate-limit).
_RETRYABLE_STATUSES = frozenset({429, 500, 502, 503, 504})
_SUCCESS_STATUSES = frozenset({200, 201, 202, 204})


class ExoscaleClient:
    """A thin, signed HTTP client for one set of Exoscale credentials.

    A single client can talk to any zone — pass ``zone=`` per call to target a
    specific one, otherwise the config default is used.
    """

    def __init__(self, config: ClientConfig, *, session: Optional[requests.Session] = None) -> None:
        self.config = config
        self._session = session or requests.Session()
        self._session.auth = ExoscaleV2Auth(config.api_key, config.api_secret)
        self._session.headers.update(
            {"Accept": "application/json", "Content-Type": "application/json"}
        )

    @classmethod
    def from_env(cls, *, zone: Optional[str] = None) -> "ExoscaleClient":
        """Convenience constructor: build config from the environment, then a client."""
        return cls(ClientConfig.from_env(zone=zone))

    # ------------------------------------------------------------------ #
    # Core request plumbing
    # ------------------------------------------------------------------ #
    def request(
        self,
        method: str,
        path: str,
        *,
        zone: Optional[str] = None,
        params: Optional[dict] = None,
        json: Any = None,
    ) -> dict:
        """Send a signed request to ``<base>/<path>`` and return the parsed body.

        ``path`` is relative to the APIv2 base (e.g. ``"security-group"`` or
        ``"instance/<id>"``). Raises :class:`NotFoundError` on 404 and
        :class:`APIError` on any other non-success status. Retries transient
        failures with exponential backoff up to ``config.max_retries``.
        """
        url = f"{self.config.base_url(zone)}/{path.lstrip('/')}"
        attempt = 0
        while True:
            response = self._session.request(
                method.upper(),
                url,
                params=params,
                json=json,
                timeout=self.config.timeout,
                verify=self.config.verify_tls,
            )
            if response.status_code in _SUCCESS_STATUSES:
                return _parse_body(response)
            if response.status_code in _RETRYABLE_STATUSES and attempt < self.config.max_retries:
                time.sleep(self.config.retry_backoff * (2**attempt))
                attempt += 1
                continue
            _raise_for_response(method, url, response)

    def get(self, path: str, *, zone: Optional[str] = None, params: Optional[dict] = None) -> dict:
        return self.request("GET", path, zone=zone, params=params)

    def post(self, path: str, *, zone: Optional[str] = None, json: Any = None) -> dict:
        return self.request("POST", path, zone=zone, json=json)

    def put(self, path: str, *, zone: Optional[str] = None, json: Any = None) -> dict:
        return self.request("PUT", path, zone=zone, json=json)

    def delete(
        self, path: str, *, zone: Optional[str] = None, params: Optional[dict] = None
    ) -> dict:
        return self.request("DELETE", path, zone=zone, params=params)

    # ------------------------------------------------------------------ #
    # Asynchronous operations
    # ------------------------------------------------------------------ #
    def wait_operation(
        self,
        operation: Union[Operation, dict, str],
        *,
        zone: Optional[str] = None,
        timeout: Optional[float] = None,
        poll_interval: float = 2.0,
    ) -> Operation:
        """Poll an async operation until it succeeds, then return the final state.

        Accepts an :class:`Operation`, a raw response dict, or an operation id.
        Raises :class:`OperationError` on failure and :class:`OperationTimeoutError`
        if it does not complete within ``timeout`` (defaults to the client timeout).

        A short run of transient poll failures (connection drops, timeouts, or a
        sporadic 404 while the operation is still propagating) is tolerated: up to
        ``config.max_poll_failures`` *consecutive* failures are swallowed before the
        underlying error is surfaced. The counter resets on every successful poll.
        """
        # If we were handed a full operation that has already settled, use it as-is
        # instead of issuing a redundant poll (many mutations return state inline).
        given = _as_operation(operation)
        if given is not None:
            self._raise_if_failed(given)
            if (given.state or "").lower() == "success":
                return given

        operation_id = _coerce_operation_id(operation)
        if not operation_id:
            # Not every mutating endpoint returns an operation; nothing to wait on.
            return given or Operation()

        deadline = time.time() + (timeout if timeout is not None else self.config.timeout)
        last = given or Operation(id=operation_id)
        consecutive_failures = 0
        while time.time() < deadline:
            try:
                last = Operation.model_validate(self.get(f"operation/{operation_id}", zone=zone))
            except (requests.exceptions.RequestException, NotFoundError):
                # Tolerate a brief run of transient poll failures rather than
                # aborting a long-running operation on a single hiccup.
                consecutive_failures += 1
                if consecutive_failures > self.config.max_poll_failures:
                    raise
                time.sleep(poll_interval)
                continue
            consecutive_failures = 0
            if (last.state or "").lower() == "success":
                return last
            self._raise_if_failed(last)
            time.sleep(poll_interval)
        raise OperationTimeoutError(
            f"Exoscale operation {operation_id} did not complete in time",
            operation_id=operation_id,
            state=(last.state or ""),
        )

    @staticmethod
    def _raise_if_failed(operation: Operation) -> None:
        """Raise :class:`OperationError` if the operation ended in a failure state."""
        state = (operation.state or "").lower()
        if state in {"failure", "timeout", "interrupted"}:
            raise OperationError(
                f"Exoscale operation {operation.id or '?'} ended in state '{state}': "
                f"{operation.reason or operation.message or 'no reason given'}",
                operation_id=operation.id or "",
                state=state,
                payload=operation.model_dump(by_alias=True),
            )


def _as_operation(operation: Union[Operation, dict, str]) -> Optional[Operation]:
    """Return an :class:`Operation` view of the input, or ``None`` for a bare id."""
    if isinstance(operation, Operation):
        return operation
    if isinstance(operation, dict):
        return Operation.model_validate(operation)
    return None


def _parse_body(response: requests.Response) -> dict:
    """Return the JSON body as a dict, or ``{}`` for empty / non-object responses."""
    if not response.content:
        return {}
    try:
        data = response.json()
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {"data": data}


def _raise_for_response(method: str, url: str, response: requests.Response) -> None:
    """Translate a non-success HTTP response into the right typed exception."""
    payload = _parse_body(response)
    message = payload.get("message") or response.text.strip() or response.reason
    detail = f"{method.upper()} {url} -> {response.status_code}: {message}"
    if response.status_code == 404:
        raise NotFoundError(detail, status_code=404, payload=payload, method=method, url=url)
    raise APIError(
        detail, status_code=response.status_code, payload=payload, method=method, url=url
    )


def _coerce_operation_id(operation: Union[Operation, dict, str]) -> str:
    """Extract an operation id from the several shapes mutating endpoints return."""
    if isinstance(operation, str):
        return operation
    if isinstance(operation, Operation):
        return operation.id or ""
    if isinstance(operation, dict):
        candidate = operation.get("id")
        if isinstance(candidate, str):
            return candidate
    return ""
