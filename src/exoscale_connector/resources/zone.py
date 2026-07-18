"""Zone resource client (read-only).

Zones are the one resource the connector otherwise hardcodes knowledge about
(:data:`~exoscale_connector.config.KNOWN_ZONES` is a static hint list). This
client returns the live answer from ``GET /zone`` instead, so tooling can
discover newly added zones without a library update.

Note the chicken-and-egg: the APIv2 host is itself zone-scoped, so you need
*one* working zone (or an endpoint override) to list all the others.

API reference: https://openapi-v2.exoscale.com/operation/operation-list-zones
"""

from __future__ import annotations

from typing import Optional

from ..models import ExoscaleModel
from ._base import ResourceClient


class Zone(ExoscaleModel):
    """An Exoscale zone (e.g. ``de-fra-1``)."""

    name: Optional[str] = None
    # The zone's API endpoint, when the API advertises it.
    api_endpoint: Optional[str] = None


class ZoneClient(ResourceClient[Zone]):
    """List Exoscale zones.

    Zones are read-only: only :meth:`list` is meaningful. The inherited
    mutating methods are not supported by the API and will fail server-side.
    """

    collection_path = "zone"
    model = Zone
    list_key = "zones"
    id_field = "name"
