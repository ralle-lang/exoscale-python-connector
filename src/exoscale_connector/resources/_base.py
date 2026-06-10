"""Generic, typed CRUD base shared by every asset-type resource client.

Each asset type subclasses :class:`ResourceClient`, declares its API path and
pydantic model, and inherits consistent ``list`` / ``get`` / ``find_by_name`` /
``create`` / ``update`` / ``delete`` behaviour — including async-operation
handling. Asset types only override what is genuinely special (extra endpoints,
non-standard payloads), keeping the per-type modules small and uniform.
"""
from __future__ import annotations

from typing import Any, Generic, List, Optional, Type, TypeVar

from ..client import ExoscaleClient
from ..errors import NotFoundError
from ..models import ExoscaleModel, Operation, to_api_payload

ModelT = TypeVar("ModelT", bound=ExoscaleModel)


class ResourceClient(Generic[ModelT]):
    """Base class for asset-type clients.

    Subclasses set :attr:`collection_path` (the APIv2 collection, e.g.
    ``"security-group"``) and :attr:`model` (the pydantic type for the resource).
    :attr:`list_key` is the JSON key holding the array in list responses; when
    left ``None`` it is inferred from the payload.
    """

    collection_path: str
    model: Type[ModelT]
    list_key: Optional[str] = None
    name_field: str = "name"
    id_field: str = "id"
    # Most mutations are asynchronous; wait for the operation by default so callers
    # get a settled resource back. Override per call with ``wait=``.
    wait_for_operations: bool = True

    def __init__(self, client: ExoscaleClient, *, zone: Optional[str] = None) -> None:
        self.client = client
        # A per-client default zone; individual calls may still override it.
        self.zone = zone

    # ------------------------------------------------------------------ #
    # Read
    # ------------------------------------------------------------------ #
    def list(self, *, zone: Optional[str] = None) -> List[ModelT]:
        """Return all resources of this type in the target zone.

        Assumes the APIv2 list endpoints return the full collection in one
        response (they are unpaginated today). If Exoscale ever introduces
        pagination, this method must grow cursor handling or it will silently
        truncate results.
        """
        payload = self.client.get(self.collection_path, zone=self._zone(zone))
        items = _extract_list(payload, self.list_key)
        return [self.model.model_validate(item) for item in items]

    def get(self, resource_id: str, *, zone: Optional[str] = None) -> ModelT:
        """Fetch a single resource by id. Raises :class:`NotFoundError` if absent."""
        payload = self.client.get(f"{self.collection_path}/{resource_id}", zone=self._zone(zone))
        return self.model.model_validate(payload)

    def find_by_name(self, name: str, *, zone: Optional[str] = None) -> Optional[ModelT]:
        """Return the first resource whose name matches, or ``None``.

        Names are not guaranteed unique by the API; this returns the first match,
        which is sufficient for the common case of human-assigned unique names.
        """
        wanted = (name or "").strip().lower()
        for item in self.list(zone=zone):
            value = getattr(item, self.name_field, None)
            if isinstance(value, str) and value.strip().lower() == wanted:
                return item
        return None

    def get_or_none(self, resource_id: str, *, zone: Optional[str] = None) -> Optional[ModelT]:
        """Like :meth:`get` but returns ``None`` instead of raising on 404."""
        try:
            return self.get(resource_id, zone=zone)
        except NotFoundError:
            return None

    # ------------------------------------------------------------------ #
    # Write
    # ------------------------------------------------------------------ #
    def create(
        self,
        payload: Any,
        *,
        zone: Optional[str] = None,
        wait: Optional[bool] = None,
    ) -> ModelT:
        """Create a resource and return it.

        ``payload`` may be a model or a dict. When the API responds with an async
        operation (the usual case) it is awaited and the new resource is re-fetched
        by its reference id; otherwise the response body is parsed directly.
        """
        zone = self._zone(zone)
        api_payload = to_api_payload(payload)
        # For name-keyed resources (e.g. ssh-key, dbaas) the API sometimes returns
        # an operation envelope without a ``reference`` — the resource id IS the
        # name we just submitted. Carry that as the fallback so the re-fetch in
        # _resolve_mutation can still hit the right endpoint.
        fallback_id: Optional[str] = None
        if self.id_field == "name" and isinstance(api_payload, dict):
            candidate = api_payload.get("name") or api_payload.get(self.name_field)
            if isinstance(candidate, str):
                fallback_id = candidate
        response = self.client.post(self.collection_path, zone=zone, json=api_payload)
        return self._resolve_mutation(response, zone=zone, wait=wait, fallback_id=fallback_id)

    def update(
        self,
        resource_id: str,
        payload: Any,
        *,
        zone: Optional[str] = None,
        wait: Optional[bool] = None,
    ) -> ModelT:
        """Update a resource (HTTP ``PUT``) and return its settled state."""
        zone = self._zone(zone)
        response = self.client.put(
            f"{self.collection_path}/{resource_id}", zone=zone, json=to_api_payload(payload)
        )
        settled = self._resolve_mutation(response, zone=zone, wait=wait, fallback_id=resource_id)
        return settled

    def delete(
        self,
        resource_id: str,
        *,
        zone: Optional[str] = None,
        wait: Optional[bool] = None,
    ) -> Operation:
        """Delete a resource by id, awaiting the async operation by default."""
        zone = self._zone(zone)
        response = self.client.delete(f"{self.collection_path}/{resource_id}", zone=zone)
        operation = Operation.model_validate(response)
        if self._should_wait(wait) and operation.id:
            operation = self.client.wait_operation(operation, zone=zone)
        return operation

    # ------------------------------------------------------------------ #
    # Internals
    # ------------------------------------------------------------------ #
    def _resolve_mutation(
        self,
        response: dict,
        *,
        zone: Optional[str],
        wait: Optional[bool],
        fallback_id: Optional[str] = None,
    ) -> ModelT:
        """Turn a create/update response into a settled, typed resource.

        Handles both async-operation envelopes and direct-resource responses.
        """
        if _looks_like_operation(response):
            operation = Operation.model_validate(response)
            if self._should_wait(wait) and operation.id:
                operation = self.client.wait_operation(operation, zone=zone)
            ref_id = operation.reference_id or fallback_id
            if ref_id:
                return self.get(ref_id, zone=zone)
            # No reference to re-fetch; surface whatever the operation carried.
            return self.model.model_validate(response)
        return self.model.model_validate(response)

    def _should_wait(self, wait: Optional[bool]) -> bool:
        return self.wait_for_operations if wait is None else wait

    def _zone(self, zone: Optional[str]) -> Optional[str]:
        return zone or self.zone


def _looks_like_operation(payload: dict) -> bool:
    """Heuristic: APIv2 async envelopes carry a ``state`` or a ``reference``."""
    return isinstance(payload, dict) and ("state" in payload or "reference" in payload)


def _extract_list(payload: dict, list_key: Optional[str]) -> List[dict]:
    """Pull the resource array out of a list response.

    Uses the declared ``list_key`` when given; otherwise infers the single
    list-valued key in the payload.
    """
    if list_key is not None:
        items = payload.get(list_key) or []
        return [i for i in items if isinstance(i, dict)]
    list_keys = [k for k, v in payload.items() if isinstance(v, list)]
    if not list_keys:
        return []
    chosen = list_keys[0] if len(list_keys) == 1 else sorted(list_keys)[0]
    return [i for i in payload.get(chosen, []) if isinstance(i, dict)]
