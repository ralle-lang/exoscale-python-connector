"""Anti-Affinity Group resource client.

API reference: https://openapi-v2.exoscale.com/group/endpoint-compute
"""

from __future__ import annotations

from pydantic import Field

from ..models import ExoscaleModel, Reference
from ._base import ResourceClient


class AntiAffinityGroup(ExoscaleModel):
    """An Exoscale anti-affinity group.

    Instances in the same anti-affinity group are placed on separate
    hypervisor hosts to reduce correlated failure risk.
    """

    id: str | None = None
    name: str | None = None
    description: str | None = None
    # Back-references to instances that are members of this group
    instances: list[Reference] = Field(default_factory=list)


class AntiAffinityGroupClient(ResourceClient[AntiAffinityGroup]):
    """Manage anti-affinity groups.

    Anti-affinity groups are create/delete-only via the API; there is no
    update endpoint, so only the inherited :meth:`create`, :meth:`delete`,
    :meth:`list`, :meth:`get`, and :meth:`find_by_name` methods apply.
    """

    collection_path = "anti-affinity-group"
    model = AntiAffinityGroup
    list_key = "anti-affinity-groups"
