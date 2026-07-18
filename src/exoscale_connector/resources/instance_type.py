"""Instance type (compute offering) resource client — read-only.

Instance types are addressed by id but humans know them as ``family.size``
(e.g. ``standard.tiny``); :meth:`InstanceTypeClient.find` resolves that form.
The wire shape matches what the live test fixtures already exercise
(``resolve_instance_type``).

API reference: https://openapi-v2.exoscale.com/group/endpoint-instance-type
"""

from __future__ import annotations

from typing import Optional

from ..models import ExoscaleModel
from ._base import ResourceClient


class InstanceType(ExoscaleModel):
    """A compute offering (CPU/memory size)."""

    id: Optional[str] = None
    family: Optional[str] = None  # e.g. "standard", "cpu", "memory", "gpu"
    size: Optional[str] = None  # e.g. "tiny", "medium", "extra-large"
    cpus: Optional[int] = None
    # Memory in bytes.
    memory: Optional[int] = None
    gpus: Optional[int] = None
    authorized: Optional[bool] = None

    @property
    def slug(self) -> str:
        """The human form ``family.size`` (e.g. ``standard.tiny``)."""
        return f"{self.family or ''}.{self.size or ''}"


class InstanceTypeClient(ResourceClient[InstanceType]):
    """List compute offerings (read-only — types are defined by Exoscale)."""

    collection_path = "instance-type"
    model = InstanceType
    list_key = "instance-types"

    def find(self, slug: str, *, zone: Optional[str] = None) -> Optional[InstanceType]:
        """Resolve a ``family.size`` slug (e.g. ``"standard.tiny"``) to a type."""
        wanted = slug.strip().lower()
        for item in self.list(zone=zone):
            if item.slug.lower() == wanted:
                return item
        return None
