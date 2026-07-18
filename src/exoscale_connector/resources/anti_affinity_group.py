"""Anti-Affinity Group resource client.

API reference: https://openapi-v2.exoscale.com/group/endpoint-compute
"""

from __future__ import annotations

from typing import List, Optional

from pydantic import Field

from ..models import ExoscaleModel, Reference
from ._base import ResourceClient


class AntiAffinityGroup(ExoscaleModel):
    """An Exoscale anti-affinity group.

    Instances in the same anti-affinity group are placed on separate
    hypervisor hosts to reduce correlated failure risk.
    """

    id: Optional[str] = None
    name: Optional[str] = None
    description: Optional[str] = None
    # Back-references to instances that are members of this group
    instances: List[Reference] = Field(default_factory=list)


class AntiAffinityGroupClient(ResourceClient[AntiAffinityGroup]):
    """Manage anti-affinity groups.

    Anti-affinity groups are create/delete-only via the API; there is no
    update endpoint, so only the inherited :meth:`create`, :meth:`delete`,
    :meth:`list`, :meth:`get`, and :meth:`find_by_name` methods apply.
    """

    collection_path = "anti-affinity-group"
    model = AntiAffinityGroup
    list_key = "anti-affinity-groups"
