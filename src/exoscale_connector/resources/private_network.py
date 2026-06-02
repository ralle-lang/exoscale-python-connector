"""Private Network resource client.

API reference: https://openapi-v2.exoscale.com/group/endpoint-private-network
"""
from __future__ import annotations

from typing import Dict, Optional

from ..models import ExoscaleModel
from ._base import ResourceClient


class PrivateNetwork(ExoscaleModel):
    """An Exoscale Private Network (layer-2 segment within a zone)."""

    id: Optional[str] = None
    name: Optional[str] = None
    description: Optional[str] = None
    # Optional DHCP range and netmask; only present when DHCP is configured.
    start_ip: Optional[str] = None       # API key: "start-ip"
    end_ip: Optional[str] = None         # API key: "end-ip"
    netmask: Optional[str] = None
    labels: Optional[Dict[str, str]] = None


class PrivateNetworkClient(ResourceClient[PrivateNetwork]):
    """Manage Exoscale Private Networks."""

    collection_path = "private-network"
    model = PrivateNetwork
    list_key = "private-networks"
