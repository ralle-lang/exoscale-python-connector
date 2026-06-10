"""Load Balancer resource client (includes service sub-resource management).

The Load Balancer has a nested sub-resource — *services* — which map incoming
listeners to a pool of backend instances. Service management mirrors the
SecurityGroupClient rule-management pattern: dedicated methods call the nested
endpoint ``load-balancer/{lb_id}/service`` rather than reusing the generic CRUD
helpers, because the service is not an independent top-level resource.

API reference: https://openapi-v2.exoscale.com/group/endpoint-network-load-balancer
"""
from __future__ import annotations

from typing import Dict, List, Optional

from pydantic import Field

from ..models import ExoscaleModel, Operation, to_api_payload
from ._base import ResourceClient


class LoadBalancerService(ExoscaleModel):
    """A listener/backend service belonging to a Load Balancer.

    A service binds a *port* on the LB's public address to a pool of instance
    targets, optionally with a healthcheck.
    """

    id: Optional[str] = None
    name: Optional[str] = None
    description: Optional[str] = None
    # "tcp" | "udp" — the transport protocol for both listener and targets
    protocol: Optional[str] = None
    # Listener port on the load balancer's public address
    port: Optional[int] = None
    # Port on the backend instances
    target_port: Optional[int] = None
    # "source-hash" | "round-robin"
    strategy: Optional[str] = None
    # Healthcheck sub-object; field names follow API kebab-case via alias generator
    healthcheck_mode: Optional[str] = None      # "tcp" | "http" | "https"
    healthcheck_port: Optional[int] = None
    healthcheck_uri: Optional[str] = None
    healthcheck_interval: Optional[int] = None
    healthcheck_timeout: Optional[int] = None
    healthcheck_retries: Optional[int] = None
    healthcheck_tls_sni: Optional[str] = None
    state: Optional[str] = None


class LoadBalancer(ExoscaleModel):
    """An Exoscale Network Load Balancer and its services."""

    id: Optional[str] = None
    name: Optional[str] = None
    description: Optional[str] = None
    ip: Optional[str] = None             # public IPv4 address
    state: Optional[str] = None
    labels: Optional[Dict[str, str]] = None
    services: List[LoadBalancerService] = Field(default_factory=list)


class LoadBalancerClient(ResourceClient[LoadBalancer]):
    """Manage Exoscale Network Load Balancers and their services."""

    collection_path = "load-balancer"
    model = LoadBalancer
    list_key = "load-balancers"

    # ------------------------------------------------------------------ #
    # Service sub-resource management
    # Paths verified against ansible/playbooks/provider/exoscale/network/
    #   provision_load_balancer_service.yml:
    #     collection_endpoint: /load-balancer/{lb_id}/service
    #     item_endpoint:       /load-balancer/{lb_id}/service/{sid}
    # ------------------------------------------------------------------ #

    def add_service(
        self,
        lb_id: str,
        service: object,
        *,
        zone: Optional[str] = None,
        wait: Optional[bool] = None,
    ) -> Operation:
        """Add a service to a load balancer.

        ``service`` may be a :class:`LoadBalancerService` or a plain dict.
        The method mirrors ``SecurityGroupClient.add_rule`` and returns the
        settled async operation.
        """
        zone = self._zone(zone)
        response = self.client.post(
            f"{self.collection_path}/{lb_id}/service",
            zone=zone,
            json=to_api_payload(service),
        )
        return self._wait_operation(response, zone=zone, wait=wait)

    def update_service(
        self,
        lb_id: str,
        service_id: str,
        payload: object,
        *,
        zone: Optional[str] = None,
        wait: Optional[bool] = None,
    ) -> Operation:
        """Update an existing service on a load balancer (HTTP PUT).

        Returns the settled async operation; re-fetch the parent LB if you
        need the updated service object.
        """
        zone = self._zone(zone)
        response = self.client.put(
            f"{self.collection_path}/{lb_id}/service/{service_id}",
            zone=zone,
            json=to_api_payload(payload),
        )
        return self._wait_operation(response, zone=zone, wait=wait)

    def delete_service(
        self,
        lb_id: str,
        service_id: str,
        *,
        zone: Optional[str] = None,
        wait: Optional[bool] = None,
    ) -> Operation:
        """Remove a service from a load balancer by service id."""
        zone = self._zone(zone)
        response = self.client.delete(
            f"{self.collection_path}/{lb_id}/service/{service_id}",
            zone=zone,
        )
        return self._wait_operation(response, zone=zone, wait=wait)

    def _wait_operation(
        self, response: dict, *, zone: Optional[str], wait: Optional[bool]
    ) -> Operation:
        """Parse an operation response and await completion unless told not to."""
        operation = Operation.model_validate(response)
        if self._should_wait(wait) and operation.id:
            operation = self.client.wait_operation(operation, zone=zone)
        return operation
