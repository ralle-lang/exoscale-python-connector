"""API key resource client.

API keys are account-global IAM credentials that grant access scoped to a
specific IAM role. They are reached through a zone host — supply a zone when
constructing the client or per-call.

Create behaviour differs from most other resource types: the POST /api-key
endpoint returns the new resource body **directly** (not an async operation
envelope), and the secret is included in that response **only once**. The
:class:`ApiKey` model therefore carries an optional :attr:`secret` field that
will be populated on create and absent on every subsequent fetch.

API reference: https://openapi-v2.exoscale.com/group/endpoint-iam
"""

from __future__ import annotations

from typing import Optional

from pydantic import Field

from ..models import ExoscaleModel, Reference
from ._base import ResourceClient


class ApiKey(ExoscaleModel):
    """An Exoscale IAM API key.

    The :attr:`key` field is the unique identifier (an opaque string, not a
    UUID).  :attr:`secret` is present **only** in the create response — it is
    never returned by list or get calls.
    """

    # The public identifier for this key (used as the item-path segment).
    key: Optional[str] = None
    name: Optional[str] = None
    # Back-reference to the IAM role this key is scoped to.
    role_id: Optional[str] = None
    role: Optional[Reference] = None
    # Populated only on create; absent (None) on all subsequent reads. This is a
    # live credential: it is excluded from repr so casual logging never echoes it,
    # but it IS still part of model_dump()/serialisation — that is the caller's
    # one chance to capture it. Don't log created ApiKey objects wholesale.
    secret: Optional[str] = Field(default=None, repr=False)


class ApiKeyClient(ResourceClient[ApiKey]):
    """Manage Exoscale IAM API keys.

    The key's unique identifier is the ``key`` string, not a UUID.
    ``id_field`` is set accordingly so :meth:`find_by_name` and the base
    ``get`` / ``delete`` methods address the correct field and URL segment.
    """

    collection_path = "api-key"
    model = ApiKey
    list_key = "api-keys"
    # Keys are addressed by their "key" string, not an "id" field.
    id_field = "key"
    name_field = "name"
