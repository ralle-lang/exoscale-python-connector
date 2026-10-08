"""Private Network resource client.

API reference: https://openapi-v2.exoscale.com/group/endpoint-private-network
"""

from __future__ import annotations

from typing import Any

from ..models import ExoscaleModel, Operation
from ._base import ResourceClient


class PrivateNetworkLease(ExoscaleModel):
    """A static DHCP lease: which instance holds which address."""

    instance_id: str | None = None
    ip: str | None = None


class PrivateNetworkOptions(ExoscaleModel):
    """DHCP options handed to instances on a managed private network."""

    dns_servers: list[str] | None = None
    ntp_servers: list[str] | None = None
    routers: list[str] | None = None
    domain_search: list[str] | None = None


class PrivateNetwork(ExoscaleModel):
    """An Exoscale Private Network (layer-2 segment within a zone)."""

    id: str | None = None
    name: str | None = None
    description: str | None = None
    # Optional DHCP range and netmask; only present when DHCP is configured.
    start_ip: str | None = None  # API key: "start-ip"
    end_ip: str | None = None  # API key: "end-ip"
    netmask: str | None = None
    labels: dict[str, str] | None = None
    options: PrivateNetworkOptions | None = None
    # Read-only: current leases, and the VXLAN ID backing the network.
    leases: list[PrivateNetworkLease] | None = None
    vni: int | None = None


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
        ip: str | None = None,
        zone: str | None = None,
        wait: bool | None = None,
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
        body: dict[str, Any] = {"instance": {"id": instance_id}}
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
        zone: str | None = None,
        wait: bool | None = None,
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
        zone: str | None,
        wait: bool | None,
    ) -> Operation:
        """Parse an attach/detach response and await completion by default."""
        operation = Operation.model_validate(response)
        if self._should_wait(wait) and operation.id:
            operation = self.client.wait_operation(operation, zone=zone)
        return operation
