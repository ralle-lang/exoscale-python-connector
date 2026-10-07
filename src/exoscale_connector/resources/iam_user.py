"""IAM user (org member) resource client.

IAM users represent organization members. They are account-global and are
reached through a zone host — supply a zone when constructing the client or
per-call.

Users are identified by UUID (``id`` field); the natural lookup key is
``email``, reflected in :attr:`name_field`.

Create and update are asynchronous; the base :meth:`create` / :meth:`update`
implementation handles the operation envelope automatically.

APIv2 has no ``GET /user/{id}`` (it 404s even for existing users), so
:meth:`IAMUserClient.get` resolves a user from the list instead.

API reference: https://openapi-v2.exoscale.com/group/endpoint-iam
"""

from __future__ import annotations

from typing import Optional

from ..errors import NotFoundError
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
    # True until an invited user accepts the invitation.
    pending: Optional[bool] = None


class IAMUserClient(ResourceClient[IAMUser]):
    """Manage Exoscale IAM users.

    ``name_field`` is set to ``"email"`` so :meth:`find_by_name` matches on
    the email address, which is the natural lookup key for org members.
    """

    collection_path = "user"
    model = IAMUser
    list_key = "users"
    name_field = "email"

    def get(self, resource_id: str, *, zone: Optional[str] = None) -> IAMUser:
        """Fetch a user by id, resolved from ``GET /user`` (there is no per-id GET).

        Also serves the re-fetch inside :meth:`create` / :meth:`update`; a
        freshly invited user is listed with ``pending`` set.
        """
        match = next((u for u in self.list(zone=zone) if u.id == resource_id), None)
        if match is None:
            raise NotFoundError(
                f"IAM user {resource_id!r} not found",
                status_code=404,
                payload={},
                method="GET",
                url=f"{self.collection_path}/{resource_id}",
            )
        return match
