"""Compute snapshot resource client.

Compute snapshots are point-in-time images of an instance's disk. The APIv2
does not expose a direct POST to ``/snapshot``; snapshots are created by calling
``POST /instance/{id}:create-snapshot`` on the source instance. This client
therefore supports **list / get / delete / export** only. The :meth:`create_from_instance`
helper wraps the instance-action endpoint for callers who want to trigger creation
here rather than through an instance client.

API reference: https://openapi-v2.exoscale.com/ (compute snapshot group)
"""

from __future__ import annotations

from typing import Optional

from ..models import ExoscaleModel, Operation, Reference
from ._base import ResourceClient


class SnapshotExport(ExoscaleModel):
    """Export metadata returned after a snapshot is exported to object storage."""

    md5sum: Optional[str] = None
    presigned_url: Optional[str] = None


class Snapshot(ExoscaleModel):
    """A compute snapshot (disk image captured from a running or stopped instance)."""

    id: Optional[str] = None
    name: Optional[str] = None
    # Size of the snapshot in GiB.
    size: Optional[int] = None
    state: Optional[str] = None
    created_at: Optional[str] = None
    # Reference to the source instance (may be absent once the instance is deleted).
    instance: Optional[Reference] = None
    export: Optional[SnapshotExport] = None


class SnapshotClient(ResourceClient[Snapshot]):
    """Manage compute snapshots.

    Snapshots cannot be created directly via this collection endpoint; use
    :meth:`create_from_instance` to trigger snapshot creation from a specific
    instance, or call ``POST /instance/{id}:create-snapshot`` via the instance
    client.
    """

    collection_path = "snapshot"
    model = Snapshot
    list_key = "snapshots"

    def create_from_instance(
        self,
        instance_id: str,
        *,
        zone: Optional[str] = None,
        wait: Optional[bool] = None,
    ) -> Snapshot:
        """Trigger a snapshot of the named instance and return the new snapshot.

        Calls ``POST /instance/{instance_id}:create-snapshot`` which is an async
        operation; by default the client waits for it to complete and re-fetches
        the snapshot by its reference id.
        """
        zone = self._zone(zone)
        response = self.client.post(
            f"instance/{instance_id}:create-snapshot",
            zone=zone,
        )
        return self._resolve_mutation(response, zone=zone, wait=wait)

    def export(
        self,
        snapshot_id: str,
        *,
        zone: Optional[str] = None,
        wait: Optional[bool] = None,
    ) -> Operation:
        """Export a snapshot to object storage (async).

        Returns the settled operation. The export presigned URL will be available
        on the snapshot object after the operation completes.
        """
        zone = self._zone(zone)
        response = self.client.post(
            f"{self.collection_path}/{snapshot_id}:export",
            zone=zone,
        )
        operation = Operation.model_validate(response)
        if self._should_wait(wait) and operation.id:
            operation = self.client.wait_operation(operation, zone=zone)
        return operation
