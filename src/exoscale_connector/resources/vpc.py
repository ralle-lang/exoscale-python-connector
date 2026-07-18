"""VPC (Virtual Private Cloud) resource client.

Covers three related resources:

- :class:`Vpc` — a private network fabric with its own routing domain
- :class:`VpcSubnet` — an IP subnet within a VPC that instances attach to
- :class:`VpcRoute` — a route entry belonging to a subnet

VPCs use the standard :class:`~._base.ResourceClient` verbs for CRUD (create /
update / delete resolve async operations). Subnets and routes are sub-resources
managed through dedicated methods — the same pattern as
:class:`~.sks.SksClusterClient` nodepools. Instances join and leave a subnet via
:meth:`VpcClient.attach_subnet` / :meth:`VpcClient.detach_subnet`.

API reference: https://openapi-v2.exoscale.com/group/endpoint-vpc
"""

from __future__ import annotations

from typing import Dict, List, Optional

from ..models import ExoscaleModel, Operation, to_api_payload
from ._base import ResourceClient


class VpcRoute(ExoscaleModel):
    """A route entry within a VPC subnet."""

    id: Optional[str] = None
    description: Optional[str] = None
    # CIDR the route matches, and the next-hop target.
    destination: Optional[str] = None
    target: Optional[str] = None
    # "Subnet" | "Vpc"
    kind: Optional[str] = None


class VpcSubnet(ExoscaleModel):
    """An IP subnet within a VPC that instances can attach to."""

    id: Optional[str] = None
    name: Optional[str] = None
    description: Optional[str] = None
    # "private"
    address_space: Optional[str] = None
    # "inet4" | "dual"
    addressfamily: Optional[str] = None
    ipv4_block: Optional[str] = None
    labels: Optional[Dict[str, str]] = None
    created_at: Optional[str] = None


class Vpc(ExoscaleModel):
    """An Exoscale VPC (private network fabric)."""

    id: Optional[str] = None
    name: Optional[str] = None
    description: Optional[str] = None
    labels: Optional[Dict[str, str]] = None
    created_at: Optional[str] = None


class VpcClient(ResourceClient[Vpc]):
    """Manage VPCs and their subnet / route sub-resources.

    VPC CRUD uses the inherited :class:`~._base.ResourceClient` verbs. Subnets,
    routes, and instance attach/detach are explicit methods because they are
    sub-resources with their own async operations.
    """

    collection_path = "vpc"
    model = Vpc
    list_key = "vpcs"

    # ------------------------------------------------------------------ #
    # Subnet sub-resource
    # ------------------------------------------------------------------ #

    def list_subnets(self, vpc_id: str, *, zone: Optional[str] = None) -> List[VpcSubnet]:
        """List a VPC's subnets (``GET vpc/{vpc_id}/subnet``)."""
        payload = self.client.get(f"{self.collection_path}/{vpc_id}/subnet", zone=self._zone(zone))
        items = payload.get("subnets") or []
        return [VpcSubnet.model_validate(i) for i in items if isinstance(i, dict)]

    def get_subnet(self, vpc_id: str, subnet_id: str, *, zone: Optional[str] = None) -> VpcSubnet:
        """Fetch one subnet by id (``GET vpc/{vpc_id}/subnet/{subnet_id}``)."""
        payload = self.client.get(
            f"{self.collection_path}/{vpc_id}/subnet/{subnet_id}",
            zone=self._zone(zone),
        )
        return VpcSubnet.model_validate(payload)

    def create_subnet(
        self,
        vpc_id: str,
        payload: object,
        *,
        zone: Optional[str] = None,
        wait: Optional[bool] = None,
    ) -> Operation:
        """Add a subnet to a VPC (``POST vpc/{vpc_id}/subnet``).

        ``payload`` needs ``name``, ``addressfamily`` (``inet4``/``dual``) and
        ``address-space`` (``private``); ``ipv4-block`` sets the CIDR. Returns
        the async operation, awaited by default.
        """
        zone = self._zone(zone)
        response = self.client.post(
            f"{self.collection_path}/{vpc_id}/subnet",
            zone=zone,
            json=to_api_payload(payload),
        )
        return self._wait_sub_operation(response, zone=zone, wait=wait)

    def update_subnet(
        self,
        vpc_id: str,
        subnet_id: str,
        payload: object,
        *,
        zone: Optional[str] = None,
        wait: Optional[bool] = None,
    ) -> Operation:
        """Update a subnet (``PUT vpc/{vpc_id}/subnet/{subnet_id}``)."""
        zone = self._zone(zone)
        response = self.client.put(
            f"{self.collection_path}/{vpc_id}/subnet/{subnet_id}",
            zone=zone,
            json=to_api_payload(payload),
        )
        return self._wait_sub_operation(response, zone=zone, wait=wait)

    def delete_subnet(
        self,
        vpc_id: str,
        subnet_id: str,
        *,
        zone: Optional[str] = None,
        wait: Optional[bool] = None,
    ) -> Operation:
        """Delete a subnet (``DELETE vpc/{vpc_id}/subnet/{subnet_id}``)."""
        zone = self._zone(zone)
        response = self.client.delete(
            f"{self.collection_path}/{vpc_id}/subnet/{subnet_id}", zone=zone
        )
        return self._wait_sub_operation(response, zone=zone, wait=wait)

    def attach_subnet(
        self,
        vpc_id: str,
        subnet_id: str,
        instance_id: str,
        *,
        zone: Optional[str] = None,
        wait: Optional[bool] = None,
    ) -> Operation:
        """Attach an instance to a subnet.

        Endpoint: ``PUT vpc/{vpc_id}/subnet/{subnet_id}/attach`` with body
        ``{"instance": {"id": instance_id}}``.
        """
        zone = self._zone(zone)
        response = self.client.put(
            f"{self.collection_path}/{vpc_id}/subnet/{subnet_id}/attach",
            zone=zone,
            json={"instance": {"id": instance_id}},
        )
        return self._wait_sub_operation(response, zone=zone, wait=wait)

    def detach_subnet(
        self,
        vpc_id: str,
        subnet_id: str,
        instance_id: str,
        *,
        zone: Optional[str] = None,
        wait: Optional[bool] = None,
    ) -> Operation:
        """Detach an instance from a subnet.

        Endpoint: ``PUT vpc/{vpc_id}/subnet/{subnet_id}/detach`` with body
        ``{"instance": {"id": instance_id}}``.
        """
        zone = self._zone(zone)
        response = self.client.put(
            f"{self.collection_path}/{vpc_id}/subnet/{subnet_id}/detach",
            zone=zone,
            json={"instance": {"id": instance_id}},
        )
        return self._wait_sub_operation(response, zone=zone, wait=wait)

    # ------------------------------------------------------------------ #
    # Route sub-resource
    # ------------------------------------------------------------------ #

    def list_routes(self, vpc_id: str, *, zone: Optional[str] = None) -> List[VpcRoute]:
        """List every route in a VPC (``GET vpc/{vpc_id}/route``)."""
        payload = self.client.get(f"{self.collection_path}/{vpc_id}/route", zone=self._zone(zone))
        items = payload.get("routes") or []
        return [VpcRoute.model_validate(i) for i in items if isinstance(i, dict)]

    def list_subnet_routes(
        self, vpc_id: str, subnet_id: str, *, zone: Optional[str] = None
    ) -> List[VpcRoute]:
        """List a subnet's routes (``GET vpc/{vpc_id}/subnet/{subnet_id}/route``)."""
        payload = self.client.get(
            f"{self.collection_path}/{vpc_id}/subnet/{subnet_id}/route",
            zone=self._zone(zone),
        )
        items = payload.get("routes") or []
        return [VpcRoute.model_validate(i) for i in items if isinstance(i, dict)]

    def create_route(
        self,
        vpc_id: str,
        subnet_id: str,
        payload: object,
        *,
        zone: Optional[str] = None,
        wait: Optional[bool] = None,
    ) -> Operation:
        """Add a route to a subnet.

        Endpoint: ``POST vpc/{vpc_id}/subnet/{subnet_id}/route``. ``payload``
        needs ``destination`` (CIDR) and ``target`` (next hop); ``description``
        is optional. The ``name`` request property was dropped upstream, so do
        not send it.
        """
        zone = self._zone(zone)
        response = self.client.post(
            f"{self.collection_path}/{vpc_id}/subnet/{subnet_id}/route",
            zone=zone,
            json=to_api_payload(payload),
        )
        return self._wait_sub_operation(response, zone=zone, wait=wait)

    def delete_route(
        self,
        vpc_id: str,
        subnet_id: str,
        route_id: str,
        *,
        zone: Optional[str] = None,
        wait: Optional[bool] = None,
    ) -> Operation:
        """Delete a route (``DELETE vpc/{vpc_id}/subnet/{subnet_id}/route/{route_id}``)."""
        zone = self._zone(zone)
        response = self.client.delete(
            f"{self.collection_path}/{vpc_id}/subnet/{subnet_id}/route/{route_id}",
            zone=zone,
        )
        return self._wait_sub_operation(response, zone=zone, wait=wait)

    # ------------------------------------------------------------------ #
    # Internal helpers
    # ------------------------------------------------------------------ #

    def _wait_sub_operation(
        self, response: dict, *, zone: Optional[str], wait: Optional[bool]
    ) -> Operation:
        """Parse a sub-resource mutation response and await completion by default."""
        operation = Operation.model_validate(response)
        if self._should_wait(wait) and operation.id:
            operation = self.client.wait_operation(operation, zone=zone)
        return operation
