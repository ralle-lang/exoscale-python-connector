"""Elastic IP resource client.

API reference: https://openapi-v2.exoscale.com/group/endpoint-elastic-ip
"""

from __future__ import annotations

from typing import Dict, Optional

from ..models import ExoscaleModel
from ._base import ResourceClient
from ._reverse_dns import ReverseDNSMixin


class ElasticIPHealthcheck(ExoscaleModel):
    """Optional healthcheck configuration attached to an Elastic IP.

    When present the NLB / anycast infrastructure will probe the associated
    instance and withdraw the address on failure.
    """

    mode: Optional[str] = None  # "tcp" | "http" | "https"
    port: Optional[int] = None
    uri: Optional[str] = None  # for http/https mode
    interval: Optional[int] = None  # seconds between probes
    timeout: Optional[int] = None  # per-probe timeout in seconds
    strikes_ok: Optional[int] = None  # consecutive successes before UP
    strikes_fail: Optional[int] = None  # consecutive failures before DOWN
    tls_sni: Optional[str] = None  # SNI hostname for https mode
    tls_skip_verify: Optional[bool] = None


class ElasticIP(ExoscaleModel):
    """An Exoscale Elastic IP (public address that can be re-assigned)."""

    id: Optional[str] = None
    ip: Optional[str] = None  # the IPv4 or IPv6 address string
    description: Optional[str] = None
    # "inet4" | "inet6" — only present on zones that support dual-stack
    addressfamily: Optional[str] = None
    healthcheck: Optional[ElasticIPHealthcheck] = None
    labels: Optional[Dict[str, str]] = None


class ElasticIPClient(ReverseDNSMixin, ResourceClient[ElasticIP]):
    """Manage Exoscale Elastic IPs, including their reverse-DNS PTR record."""

    collection_path = "elastic-ip"
    model = ElasticIP
    list_key = "elastic-ips"
    _rdns_kind = "elastic-ip"
