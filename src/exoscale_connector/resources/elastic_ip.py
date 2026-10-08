"""Elastic IP resource client.

API reference: https://openapi-v2.exoscale.com/group/endpoint-elastic-ip
"""

from __future__ import annotations

from ..models import ExoscaleModel
from ._base import ResourceClient
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


class ElasticIPClient(ReverseDNSMixin, ResourceClient[ElasticIP]):
    """Manage Exoscale Elastic IPs, including their reverse-DNS PTR record."""

    collection_path = "elastic-ip"
    model = ElasticIP
    list_key = "elastic-ips"
    _rdns_kind = "elastic-ip"
