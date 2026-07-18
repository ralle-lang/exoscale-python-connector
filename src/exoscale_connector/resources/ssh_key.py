"""SSH key resource client.

SSH keys are account-global resources that can be injected into compute
instances at provision time. They are reached through a zone host — supply a
zone when constructing the client or per-call.

Unlike most resources, SSH keys are **identified by name** rather than a UUID.
:attr:`id_field` and :attr:`name_field` are both set to ``"name"`` so the base
:meth:`get`, :meth:`delete`, and :meth:`find_by_name` methods address the
correct URL segment and model attribute.

API reference: https://openapi-v2.exoscale.com/group/endpoint-ssh-key
"""

from __future__ import annotations

from typing import Optional

from ..models import ExoscaleModel
from ._base import ResourceClient


class SSHKey(ExoscaleModel):
    """An Exoscale SSH public key."""

    name: Optional[str] = None
    fingerprint: Optional[str] = None
    # The public key material. Present on import; may be absent on list/get
    # responses depending on the API version.
    public_key: Optional[str] = None


class SSHKeyClient(ResourceClient[SSHKey]):
    """Manage Exoscale SSH keys.

    SSH keys have no UUID: ``name`` is both the resource identifier used in API
    paths (``/ssh-key/{name}``) and the lookup field for :meth:`find_by_name`.
    """

    collection_path = "ssh-key"
    model = SSHKey
    list_key = "ssh-keys"
    # Name is the sole identifier; used as the path segment in get/delete.
    id_field = "name"
    name_field = "name"
