"""Private Network resource client.

API reference: https://openapi-v2.exoscale.com/group/endpoint-private-network
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from ..models import ExoscaleModel, Operation
from ._base import ResourceClient


class PrivateNetwork(ExoscaleModel):
    """An Exoscale Private Network (layer-2 segment within a zone)."""

    id: Optional[str] = None
    name: Optional[str] = None
    description: Optional[str] = None
    # Optional DHCP range and netmask; only present when DHCP is configured.
    start_ip: Optional[str] = None  # API key: "start-ip"
    end_ip: Optional[str] = None  # API key: "end-ip"
    netmask: Optional[str] = None
    labels: Optional[Dict[str, str]] = None


class PrivateNetworkClient(ResourceClient[PrivateNetwork]):
    """Manage Exoscale Private Networks."""

    collection_path = "private-network"
    model = PrivateNetwork
    list_key = "private-networks"

    # ------------------------------------------------------------------ #
    # Instance membership
    # ------------------------------------------------------------------ #

    def attach_instance(
        self,
        network_id: str,
        instance_id: str,
        *,
        ip: Optional[str] = None,
        zone: Optional[str] = None,
        wait: Optional[bool] = None,
    ) -> Operation:
        """Attach a compute instance to this private network.

        Colon-action endpoint ``PUT private-network/{id}:attach`` with body
        ``{"instance": {"id": <instance_id>}}``. This is how an instance joins a
        private network — the membership lives on the network side, not on the
        instance's own update endpoint. Returns the async operation, awaited by
        default.

        On a *managed* network you may pin a static lease with ``ip`` (it must
        fall inside the network's ``start-ip``/``end-ip`` range); omit it to let
        DHCP assign one. ``ip`` is ignored by unmanaged networks.
        """
        zone = self._zone(zone)
        body: Dict[str, Any] = {"instance": {"id": instance_id}}
        if ip is not None:
            body["ip"] = ip
        response = self.client.put(
            f"{self.collection_path}/{network_id}:attach",
            zone=zone,
            json=body,
        )
        return self._wait_membership_operation(response, zone=zone, wait=wait)

    def detach_instance(
        self,
        network_id: str,
        instance_id: str,
        *,
        zone: Optional[str] = None,
        wait: Optional[bool] = None,
    ) -> Operation:
        """Detach a compute instance from this private network.

        Colon-action endpoint ``PUT private-network/{id}:detach`` with body
        ``{"instance": {"id": <instance_id>}}``. Returns the async operation,
        awaited by default.
        """
        zone = self._zone(zone)
        response = self.client.put(
            f"{self.collection_path}/{network_id}:detach",
            zone=zone,
            json={"instance": {"id": instance_id}},
        )
        return self._wait_membership_operation(response, zone=zone, wait=wait)

    def _wait_membership_operation(
        self,
        response: dict,
        *,
        zone: Optional[str],
        wait: Optional[bool],
    ) -> Operation:
        """Parse an attach/detach response and await completion by default."""
        operation = Operation.model_validate(response)
        if self._should_wait(wait) and operation.id:
            operation = self.client.wait_operation(operation, zone=zone)
        return operation
