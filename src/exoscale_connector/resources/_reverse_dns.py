"""Reverse-DNS (PTR record) management shared by instances and elastic IPs.

The APIv2 exposes reverse DNS under a dedicated path family,
``/reverse-dns/{kind}/{id}`` (kind being ``instance`` or ``elastic-ip``), not
nested under the resource itself.

.. warning::
   These endpoints are implemented from the API reference and are **pending
   live verification** — they are not yet covered by a recorded live-test run.
"""
from __future__ import annotations

from typing import Optional

from ..errors import NotFoundError
from ..models import Operation


class ReverseDNSMixin:
    """Mixin for :class:`~exoscale_connector.resources._base.ResourceClient`
    subclasses whose resources support PTR records.

    Subclasses set ``_rdns_kind`` to the path token (``"instance"`` or
    ``"elastic-ip"``).
    """

    _rdns_kind: str

    def get_reverse_dns(self, resource_id: str, *, zone: Optional[str] = None) -> Optional[str]:
        """Return the PTR domain name for the resource, or ``None`` if unset."""
        try:
            payload = self.client.get(  # type: ignore[attr-defined]
                f"reverse-dns/{self._rdns_kind}/{resource_id}",
                zone=self._zone(zone),  # type: ignore[attr-defined]
            )
        except NotFoundError:
            return None
        value = payload.get("domain-name")
        # Defensive: some response shapes nest the record one level down.
        if isinstance(value, dict):
            value = value.get("domain-name")
        return value if isinstance(value, str) else None

    def set_reverse_dns(
        self,
        resource_id: str,
        domain_name: str,
        *,
        zone: Optional[str] = None,
        wait: Optional[bool] = None,
    ) -> Operation:
        """Set the PTR record (``POST /reverse-dns/{kind}/{id}``).

        The verb is POST, not PUT — the spec-symmetric PUT returns 404
        (confirmed live 2026-06-10).
        """
        zone = self._zone(zone)  # type: ignore[attr-defined]
        response = self.client.post(  # type: ignore[attr-defined]
            f"reverse-dns/{self._rdns_kind}/{resource_id}",
            zone=zone,
            json={"domain-name": domain_name},
        )
        return self._settle_operation(response, zone=zone, wait=wait)

    def delete_reverse_dns(
        self,
        resource_id: str,
        *,
        zone: Optional[str] = None,
        wait: Optional[bool] = None,
    ) -> Operation:
        """Remove the PTR record (``DELETE /reverse-dns/{kind}/{id}``)."""
        zone = self._zone(zone)  # type: ignore[attr-defined]
        response = self.client.delete(  # type: ignore[attr-defined]
            f"reverse-dns/{self._rdns_kind}/{resource_id}", zone=zone
        )
        return self._settle_operation(response, zone=zone, wait=wait)

    def _settle_operation(
        self, response: dict, *, zone: Optional[str], wait: Optional[bool]
    ) -> Operation:
        operation = Operation.model_validate(response)
        if self._should_wait(wait) and operation.id:  # type: ignore[attr-defined]
            operation = self.client.wait_operation(operation, zone=zone)  # type: ignore[attr-defined]
        return operation
