"""Deploy Target resource client (read-only).

Deploy targets are placement targets an instance can be pinned to at creation
time — an ``edge`` location or a ``dedicated`` host. They are provisioned by
Exoscale, not by API callers, so this client is read-only: use :meth:`list` /
:meth:`get` to discover a target id, then pass it into
:meth:`~exoscale_connector.resources.instance.InstanceClient.create` as
``{"deploy-target": {"id": "<target-id>"}}``.

API reference: https://openapi-v2.exoscale.com/group/endpoint-deploy-target
"""

from __future__ import annotations

from ..models import ExoscaleModel
from ._base import ResourceClient


class DeployTarget(ExoscaleModel):
    """An Exoscale deploy target (instance placement target)."""

    id: str | None = None
    name: str | None = None
    description: str | None = None
    # "edge" | "dedicated"
    type: str | None = None


class DeployTargetClient(ResourceClient[DeployTarget]):
    """List and fetch Exoscale deploy targets.

    Read-only: only :meth:`list` and :meth:`get` are meaningful. Deploy targets
    are created by Exoscale, so the inherited mutating methods will fail
    server-side.
    """

    collection_path = "deploy-target"
    model = DeployTarget
    list_key = "deploy-targets"
