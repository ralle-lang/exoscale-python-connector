"""Compute template resource client.

Templates are the boot images instances are created from. Listing supports the
``visibility`` filter (``"public"`` for Exoscale's stock images, ``"private"``
for templates you registered). Registering a custom template is a normal
``create`` with the template's source URL and checksum.

The list/get wire shapes here match what the live test fixtures already
exercise (``resolve_linux_template``); register/delete are pending live
verification.

API reference: https://openapi-v2.exoscale.com/group/endpoint-template
"""
from __future__ import annotations

from typing import List, Optional

from ..models import ExoscaleModel
from ._base import ResourceClient


class Template(ExoscaleModel):
    """A compute template (boot image)."""

    id: Optional[str] = None
    name: Optional[str] = None
    description: Optional[str] = None
    family: Optional[str] = None        # e.g. "Linux Ubuntu", used for OS matching
    version: Optional[str] = None
    # Minimum disk size the template requires, in bytes.
    size: Optional[int] = None
    visibility: Optional[str] = None    # "public" | "private"
    # Registration source (private templates).
    url: Optional[str] = None
    checksum: Optional[str] = None
    boot_mode: Optional[str] = None     # "legacy" | "uefi"
    default_user: Optional[str] = None
    ssh_key_enabled: Optional[bool] = None
    password_enabled: Optional[bool] = None
    build: Optional[str] = None
    created_at: Optional[str] = None


class TemplateClient(ResourceClient[Template]):
    """List, register and delete compute templates."""

    collection_path = "template"
    model = Template
    list_key = "templates"

    def list(  # type: ignore[override]
        self,
        *,
        zone: Optional[str] = None,
        labels: Optional[dict] = None,
        visibility: Optional[str] = None,
    ) -> List[Template]:
        """List templates, optionally filtered by ``visibility``.

        Without ``visibility`` the API returns its default set (public
        templates). Pass ``"private"`` for templates registered in your
        organisation. ``labels`` filtering is accepted for signature
        compatibility but templates carry no labels today.
        """
        params = {"visibility": visibility} if visibility else None
        payload = self.client.get(self.collection_path, zone=self._zone(zone), params=params)
        items = payload.get(self.list_key) or []
        return [self.model.model_validate(item) for item in items if isinstance(item, dict)]

    def find_linux(self, *, zone: Optional[str] = None) -> Optional[Template]:
        """Return the smallest public Linux template in the zone, or ``None``.

        Mirrors the selection logic the live tests use: filter by family
        containing "linux", then prefer the smallest required disk size.
        """
        candidates = [
            t for t in self.list(zone=zone) if "linux" in (t.family or "").lower()
        ]
        if not candidates:
            return None
        candidates.sort(key=lambda t: t.size if t.size is not None else float("inf"))
        return candidates[0]
