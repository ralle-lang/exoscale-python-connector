"""IAM user (org member) resource client.

IAM users represent organization members. They are account-global and are
reached through a zone host — supply a zone when constructing the client or
per-call.

Users are identified by UUID (``id`` field); the natural lookup key is
``email``, reflected in :attr:`name_field`.

Create and update are asynchronous; the base :meth:`create` / :meth:`update`
implementation handles the operation envelope automatically.

API reference: https://openapi-v2.exoscale.com/group/endpoint-iam
"""
from __future__ import annotations

from typing import Optional

from ..models import ExoscaleModel, Reference
from ._base import ResourceClient


class IAMUser(ExoscaleModel):
    """An Exoscale IAM user (organization member)."""

    id: Optional[str] = None
    # Email is the human-readable unique identifier within the org.
    email: Optional[str] = None
    # The IAM role assigned to this user.
    role_id: Optional[str] = None
    role: Optional[Reference] = None


class IAMUserClient(ResourceClient[IAMUser]):
    """Manage Exoscale IAM users.

    ``name_field`` is set to ``"email"`` so :meth:`find_by_name` matches on
    the email address, which is the natural lookup key for org members.
    """

    collection_path = "user"
    model = IAMUser
    list_key = "users"
    name_field = "email"
