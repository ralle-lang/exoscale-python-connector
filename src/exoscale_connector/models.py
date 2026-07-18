"""Shared pydantic model infrastructure.

The Exoscale APIv2 uses kebab-case JSON field names (e.g. ``flow-direction``,
``start-port``). To keep Python attributes idiomatic, every model derives from
:class:`ExoscaleModel`, which maps snake_case attributes to kebab-case aliases
automatically. Serialise outbound payloads with ``model_dump(by_alias=True,
exclude_none=True)`` (or the :func:`to_api_payload` helper).
"""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, ConfigDict


def to_kebab(name: str) -> str:
    """Translate a snake_case attribute name to its kebab-case API alias."""
    return name.replace("_", "-")


class ExoscaleModel(BaseModel):
    """Base model for all API request/response objects.

    ``extra="allow"`` keeps unknown server fields instead of dropping them, so the
    connector keeps working when the API gains new attributes ahead of this library.
    """

    model_config = ConfigDict(
        alias_generator=to_kebab,
        populate_by_name=True,
        extra="allow",
    )

    def to_api_payload(self) -> dict:
        """Render this model as a request body the API will accept."""
        return self.model_dump(by_alias=True, exclude_none=True)


class Reference(ExoscaleModel):
    """A lightweight pointer to another resource (``{"id": ...}``)."""

    id: Optional[str] = None
    link: Optional[str] = None


class Operation(ExoscaleModel):
    """An asynchronous API operation envelope returned by mutating endpoints.

    ``state`` transitions through ``pending`` to one of ``success`` / ``failure`` /
    ``timeout``; ``reference`` points at the resource the operation acted on.
    """

    id: Optional[str] = None
    state: Optional[str] = None
    reference: Optional[Reference] = None
    reason: Optional[str] = None
    message: Optional[str] = None

    @property
    def reference_id(self) -> Optional[str]:
        """The id of the affected resource, if the operation carries a reference."""
        return self.reference.id if self.reference else None


def to_api_payload(value: Any) -> Any:
    """Coerce a model, dict, or ``None`` into a JSON-serialisable request body.

    Accepts an :class:`ExoscaleModel`, a plain dict, or ``None`` so resource
    methods can take either typed models or raw dicts from callers.
    """
    if value is None:
        return None
    if isinstance(value, ExoscaleModel):
        return value.to_api_payload()
    if isinstance(value, BaseModel):
        return value.model_dump(by_alias=True, exclude_none=True)
    if isinstance(value, dict):
        return {k: v for k, v in value.items() if v is not None}
    raise TypeError(f"Cannot build an API payload from {type(value)!r}")
