"""Reset an optional field to its default (``DELETE /{collection}/{id}/{field}``).

Several APIv2 resources expose one ``reset-<type>-field`` endpoint that clears
an optional field — labels, description, attached groups — instead of making
callers send an explicit empty value through ``update``. Which fields are
resettable varies per type and is listed in the API reference; the connector
passes ``field`` through unchanged and lets the API reject anything else.
"""

from __future__ import annotations

from typing import Protocol

from ..client import ExoscaleClient
from ..models import Operation


class _Client(Protocol):
    client: ExoscaleClient
    collection_path: str

    def _zone(self, zone: str | None) -> str | None: ...

    def _should_wait(self, wait: bool | None) -> bool: ...


class ResetFieldMixin:
    """Mixin for clients whose resource has a ``reset-*-field`` endpoint."""

    def reset_field(
        self: _Client,
        resource_id: str,
        field: str,
        *,
        zone: str | None = None,
        wait: bool | None = None,
    ) -> Operation:
        """Reset ``field`` (wire name, e.g. ``"labels"``) to its default.

        Endpoint: ``DELETE {collection}/{resource_id}/{field}``. Returns the
        async operation, awaited by default.
        """
        zone = self._zone(zone)
        response = self.client.delete(f"{self.collection_path}/{resource_id}/{field}", zone=zone)
        operation = Operation.model_validate(response)
        if self._should_wait(wait) and operation.id:
            operation = self.client.wait_operation(operation, zone=zone)
        return operation
