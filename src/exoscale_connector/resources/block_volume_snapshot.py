"""Block storage snapshot resource client.

A block storage snapshot is a point-in-time copy of a block storage volume.
Unlike compute snapshots (which are captured from instance disks), these live
entirely within the block storage subsystem and are created via a volume action
rather than a direct POST to this collection.

The APIv2 does not expose ``POST /block-storage-snapshot`` for creation; use
:meth:`BlockVolumeSnapshotClient.create_from_volume` which calls
``POST /block-storage/{volume_id}:create-snapshot``, or use the
:meth:`~exoscale_connector.resources.block_volume.BlockVolumeClient.create_snapshot`
helper on the volume client.

API reference: https://openapi-v2.exoscale.com/ (block storage group)
"""

from __future__ import annotations

from ..models import ExoscaleModel, Operation
from ._base import ResourceClient


class BlockVolumeSnapshot(ExoscaleModel):
    """A snapshot derived from a block storage volume."""

    id: str | None = None
    name: str | None = None
    # Size of the snapshot in GiB.
    size: int | None = None
    state: str | None = None
    created_at: str | None = None
    labels: dict[str, str] | None = None


class BlockVolumeSnapshotClient(ResourceClient[BlockVolumeSnapshot]):
    """Manage block storage snapshots.

    Direct creation via this collection is not supported by the APIv2. Use
    :meth:`create_from_volume` or the volume client's ``create_snapshot`` method
    to trigger snapshot creation from a specific block volume.
    """

    collection_path = "block-storage-snapshot"
    model = BlockVolumeSnapshot
    # Confirmed from Ansible playbooks: the list response uses this exact key.
    list_key = "block-storage-snapshots"

    def create_from_volume(
        self,
        volume_id: str,
        *,
        zone: str | None = None,
        wait: bool | None = None,
    ) -> BlockVolumeSnapshot:
        """Trigger a snapshot of the named block storage volume.

        Calls ``POST /block-storage/{volume_id}:create-snapshot`` (async); by
        default the client waits for the operation to settle and re-fetches the
        new snapshot by its reference id.
        """
        zone = self._zone(zone)
        response = self.client.post(
            f"block-storage/{volume_id}:create-snapshot",
            zone=zone,
        )
        return self._resolve_mutation(response, zone=zone, wait=wait)

    def update(
        self,
        resource_id: str,
        payload: object,
        *,
        zone: str | None = None,
        wait: bool | None = None,
    ) -> BlockVolumeSnapshot:
        """Update snapshot properties (e.g. name, labels) via ``PUT``.

        Delegates to the base ``update`` implementation; documented here so it
        is visible alongside the snapshot-specific helpers.
        """
        return super().update(resource_id, payload, zone=zone, wait=wait)

    def _settle_operation(
        self,
        response: dict,
        *,
        zone: str | None,
        wait: bool | None,
    ) -> Operation:
        """Parse and optionally await an async operation envelope."""
        operation = Operation.model_validate(response)
        if self._should_wait(wait) and operation.id:
            operation = self.client.wait_operation(operation, zone=zone)
        return operation
