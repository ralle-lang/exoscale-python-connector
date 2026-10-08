"""Compute template resource client.

Templates are the boot images instances are created from. Listing supports the
``visibility`` filter (``"public"`` for Exoscale's stock images, ``"private"``
for templates you registered). Registering a custom template is a normal
``create`` with the template's source URL and checksum.

The list/get wire shapes here match what the live test fixtures already
exercise (``resolve_linux_template``); register/delete live-verified
2026-06-11 (``test_template_register_delete``).

API reference: https://openapi-v2.exoscale.com/group/endpoint-template
"""

from __future__ import annotations

import builtins

from ..models import ExoscaleModel
from ._base import ResourceClient


class Template(ExoscaleModel):
    """A compute template (boot image)."""

    id: str | None = None
    name: str | None = None
    description: str | None = None
    family: str | None = None  # e.g. "Linux Ubuntu", used for OS matching
    version: str | None = None
    # Minimum disk size the template requires, in bytes.
    size: int | None = None
    visibility: str | None = None  # "public" | "private"
    # Registration source (private templates).
    url: str | None = None
    checksum: str | None = None
    boot_mode: str | None = None  # "legacy" | "uefi"
    default_user: str | None = None
    ssh_key_enabled: bool | None = None
    password_enabled: bool | None = None
    build: str | None = None
    created_at: str | None = None


class TemplateClient(ResourceClient[Template]):
    """List, register and delete compute templates."""

    collection_path = "template"
    model = Template
    list_key = "templates"

    def list(  # type: ignore[override]
        self,
        *,
        zone: str | None = None,
        labels: dict | None = None,
        visibility: str | None = None,
    ) -> builtins.list[Template]:
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

    def find_linux(self, *, zone: str | None = None) -> Template | None:
        """Return the smallest public Linux template in the zone, or ``None``.

        Mirrors the selection logic the live tests use: filter by family
        containing "linux", then prefer the smallest required disk size.
        """
        candidates = [t for t in self.list(zone=zone) if "linux" in (t.family or "").lower()]
        if not candidates:
            return None
        candidates.sort(key=lambda t: t.size if t.size is not None else float("inf"))
        return candidates[0]
