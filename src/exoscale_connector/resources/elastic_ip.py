"""Elastic IP resource client.

API reference: https://openapi-v2.exoscale.com/group/endpoint-elastic-ip
"""

from __future__ import annotations

from ..models import ExoscaleModel, Operation
from ._base import ResourceClient
from ._reset_field import ResetFieldMixin
from ._reverse_dns import ReverseDNSMixin


class ElasticIPHealthcheck(ExoscaleModel):
    """Optional healthcheck configuration attached to an Elastic IP.

    When present the NLB / anycast infrastructure will probe the associated
    instance and withdraw the address on failure.
    """

    mode: str | None = None  # "tcp" | "http" | "https"
    port: int | None = None
    uri: str | None = None  # for http/https mode
    interval: int | None = None  # seconds between probes
    timeout: int | None = None  # per-probe timeout in seconds
    strikes_ok: int | None = None  # consecutive successes before UP
    strikes_fail: int | None = None  # consecutive failures before DOWN
    tls_sni: str | None = None  # SNI hostname for https mode
    tls_skip_verify: bool | None = None


class ElasticIP(ExoscaleModel):
    """An Exoscale Elastic IP (public address that can be re-assigned)."""

    id: str | None = None
    ip: str | None = None  # the IPv4 or IPv6 address string
    description: str | None = None
    # "inet4" | "inet6" — only present on zones that support dual-stack
    addressfamily: str | None = None
    healthcheck: ElasticIPHealthcheck | None = None
    labels: dict[str, str] | None = None


class ElasticIPClient(ResetFieldMixin, ReverseDNSMixin, ResourceClient[ElasticIP]):
    """Manage Exoscale Elastic IPs, including their reverse-DNS PTR record."""

    collection_path = "elastic-ip"
    model = ElasticIP
    list_key = "elastic-ips"
    # EIPs have no ``name``; ``description`` is their only human label, so
    # find_by_name / ensure / CLI ``find --name`` match on it.
    name_field = "description"
    _rdns_kind = "elastic-ip"

    def attach_instance(
        self,
        elastic_ip_id: str,
        instance_id: str,
        *,
        zone: str | None = None,
        wait: bool | None = None,
    ) -> Operation:
        """Attach the elastic IP to an instance (``PUT elastic-ip/{id}:attach``).

        The instance still has to configure the address on an interface;
        Exoscale does not do that inside the guest.
        """
        zone = self._zone(zone)
        response = self.client.put(
            f"{self.collection_path}/{elastic_ip_id}:attach",
            zone=zone,
            json={"instance": {"id": instance_id}},
        )
        return self._await(response, zone=zone, wait=wait)

    def detach_instance(
        self,
        elastic_ip_id: str,
        instance_id: str,
        *,
        zone: str | None = None,
        wait: bool | None = None,
    ) -> Operation:
        """Detach the elastic IP from an instance (``PUT elastic-ip/{id}:detach``)."""
        zone = self._zone(zone)
        response = self.client.put(
            f"{self.collection_path}/{elastic_ip_id}:detach",
            zone=zone,
            json={"instance": {"id": instance_id}},
        )
        return self._await(response, zone=zone, wait=wait)

    def _await(self, response: dict, *, zone: str | None, wait: bool | None) -> Operation:
        operation = Operation.model_validate(response)
        if self._should_wait(wait) and operation.id:
            operation = self.client.wait_operation(operation, zone=zone)
        return operation
