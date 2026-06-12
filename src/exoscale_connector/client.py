"""The low-level HTTP client for the Exoscale APIv2.

:class:`ExoscaleClient` owns a signed ``requests`` session and exposes verb
helpers plus asynchronous-operation polling. Resource classes
(:mod:`exoscale_connector.resources`) sit on top of it and add typed, per-asset
behaviour — application code normally uses those rather than this client directly.
"""
from __future__ import annotations

import logging
import random
import time
from typing import Any, Optional, Union

import requests

from .auth import ExoscaleV2Auth
from .config import ClientConfig
from .errors import APIError, NotFoundError, OperationError, OperationTimeoutError
from .models import Operation

# Retry policy is split by HTTP method semantics. For idempotent verbs any
# transient server / rate-limit status — or a connection-level failure — is safe
# to retry. POST is not idempotent: a 500/502/504 or a dropped connection does not
# guarantee the mutation was not applied server-side, so blindly retrying can
# create duplicate resources. Only 429 — where the server explicitly refused to
# process the request — is retried for mutations. The retryable *status* sets are
# configurable per client (ClientConfig); the method split is fixed policy.
_IDEMPOTENT_METHODS = frozenset({"GET", "HEAD", "OPTIONS", "DELETE", "PUT"})
_SUCCESS_STATUSES = frozenset({200, 201, 202, 204})
# Upper bound on how long a server-sent Retry-After may stall a single retry.
_MAX_RETRY_AFTER = 60.0
# Connection-level failures treated as transient (no HTTP response was received).
# Retried for idempotent verbs only, on the same backoff/max_retries budget.
_TRANSIENT_EXCEPTIONS = (
    requests.exceptions.ConnectionError,
    requests.exceptions.Timeout,
    requests.exceptions.ChunkedEncodingError,
)

# Debug logging for request/response tracing. Deliberately logs only
# method/URL/status/duration — never headers (Authorization carries the
# signature) and never bodies (create responses can carry one-time secrets).
# Enable with: logging.getLogger("exoscale_connector").setLevel(logging.DEBUG)
logger = logging.getLogger("exoscale_connector")


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
        max_retries: Optional[int] = None,
    ) -> dict:
        """Send a signed request to ``<base>/<path>`` and return the parsed body.

        ``path`` is relative to the APIv2 base (e.g. ``"security-group"`` or
        ``"instance/<id>"``). Raises :class:`NotFoundError` on 404 and
        :class:`APIError` on any other non-success status. Retries transient
        failures — retryable HTTP statuses *and* connection-level errors (dropped
        connections, read timeouts) — with jittered exponential backoff up to
        ``config.max_retries``. Non-idempotent verbs (POST) are only retried on
        429, where the server explicitly did not process the request; a 5xx or a
        dropped connection on a POST surfaces immediately, since the mutation may
        already have been applied and a blind retry could duplicate it.

        ``max_retries`` overrides the config retry budget for this one call; pass
        ``0`` to issue a single attempt (used by the operation poll loop, which
        owns its own transient-failure tolerance via ``config.max_poll_failures``).
        """
        url = f"{self.config.base_url(zone)}/{path.lstrip('/')}"
        verb = method.upper()
        idempotent = verb in _IDEMPOTENT_METHODS
        budget = self.config.max_retries if max_retries is None else max_retries
        retryable = (
            self.config.retryable_statuses_idempotent
            if idempotent
            else self.config.retryable_statuses_mutating
        )
        attempt = 0
        while True:
            started = time.monotonic()
            try:
                response = self._session.request(
                    verb,
                    url,
                    params=params,
                    json=json,
                    timeout=self.config.timeout,
                    verify=self.config.verify_tls,
                )
            except _TRANSIENT_EXCEPTIONS as exc:
                # No response arrived. Safe to retry only for idempotent verbs;
                # for POST the mutation may have landed, so surface the error.
                if idempotent and attempt < budget:
                    logger.debug("%s %s -> %s; retrying", verb, url, type(exc).__name__)
                    time.sleep(_backoff_delay(attempt, self.config.retry_backoff))
                    attempt += 1
                    continue
                raise
            logger.debug(
                "%s %s -> %s (%.0f ms)",
                verb,
                url,
                response.status_code,
                (time.monotonic() - started) * 1000,
            )
            if response.status_code in _SUCCESS_STATUSES:
                return _parse_body(response)
            if response.status_code in retryable and attempt < budget:
                time.sleep(_retry_delay(response, attempt, self.config.retry_backoff))
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
        if it does not complete within ``timeout`` (defaults to
        ``config.operation_timeout``).

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

        deadline = time.time() + (
            timeout if timeout is not None else self.config.operation_timeout
        )
        last = given or Operation(id=operation_id)
        consecutive_failures = 0
        while time.time() < deadline:
            try:
                # Single attempt: this loop is itself the retry authority for
                # polling (max_poll_failures, with reset-on-success), so it must
                # not compound with the per-request retry budget.
                last = Operation.model_validate(
                    self.request("GET", f"operation/{operation_id}", zone=zone, max_retries=0)
                )
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


def _backoff_delay(attempt: int, backoff: float) -> float:
    """Full-jitter exponential backoff, keeping a fleet from retrying in lockstep."""
    return random.uniform(0, backoff * (2**attempt))


def _retry_delay(response: requests.Response, attempt: int, backoff: float) -> float:
    """Pick the sleep before the next retry after an HTTP error response.

    A server-sent ``Retry-After`` (seconds form) wins over our own backoff —
    the server knows its rate-limit window better than we do — capped so a
    pathological header can't stall the client. Otherwise fall back to
    full-jitter exponential backoff (the only option for connection-level
    errors, where there is no response to read a header from).
    """
    header = response.headers.get("Retry-After", "")
    if header.strip().isdigit():
        return min(float(header.strip()), _MAX_RETRY_AFTER)
    return _backoff_delay(attempt, backoff)


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
