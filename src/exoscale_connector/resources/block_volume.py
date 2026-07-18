"""Block storage volume resource client.

Block storage volumes are persistent, zone-local block devices that can be
attached to at most one compute instance at a time. The APIv2 exposes full CRUD
plus attach / detach / resize helpers, all of which are async operations.

API reference: https://openapi-v2.exoscale.com/ (block storage group)
"""

from __future__ import annotations

from typing import Dict, List, Optional

from pydantic import Field

from ..models import ExoscaleModel, Operation, Reference, to_api_payload
from ._base import ResourceClient


class BlockVolumeSnapshotRef(ExoscaleModel):
    """Lightweight reference to a block-storage snapshot attached to a volume."""

    id: Optional[str] = None
    name: Optional[str] = None


class BlockVolume(ExoscaleModel):
    """A block storage volume."""

    id: Optional[str] = None
    name: Optional[str] = None
    # Capacity of the volume in GiB.
    size: Optional[int] = None
    state: Optional[str] = None
    created_at: Optional[str] = None
    # Physical block size of the volume in bytes (typically 512 or 4096).
    blocksize: Optional[int] = None
    labels: Optional[Dict[str, str]] = None
    # Instance the volume is currently attached to, if any.
    instance: Optional[Reference] = None
    # Snapshots derived from this volume. The live API uses the wrapper key
    # ``block-storage-snapshots`` here (not the auto-generated kebab alias
    # ``snapshots``), so we override the alias explicitly. Without this the
    # field is always ``None`` even when the volume has snapshots.
    snapshots: Optional[List[BlockVolumeSnapshotRef]] = Field(
        default=None, alias="block-storage-snapshots"
    )


class BlockVolumeClient(ResourceClient[BlockVolume]):
    """Manage block storage volumes, including attach / detach / resize operations."""

    collection_path = "block-storage"
    model = BlockVolume
    # The live API returns the volume array under "block-storage-volumes".
    list_key = "block-storage-volumes"

    def attach(
        self,
        volume_id: str,
        instance_id: str,
        *,
        zone: Optional[str] = None,
        wait: Optional[bool] = None,
    ) -> Operation:
        """Attach a volume to a compute instance (async).

        ``instance_id`` is the id of the target instance.
        """
        # Exoscale action endpoints use the colon-action syntax, e.g.
        # ``/block-storage/{id}:attach`` — the same pattern as :create-snapshot.
        zone = self._zone(zone)
        response = self.client.put(
            f"{self.collection_path}/{volume_id}:attach",
            zone=zone,
            json={"instance": {"id": instance_id}},
        )
        return self._settle_operation(response, zone=zone, wait=wait)

    def detach(
        self,
        volume_id: str,
        *,
        zone: Optional[str] = None,
        wait: Optional[bool] = None,
    ) -> Operation:
        """Detach a volume from its currently attached instance (async)."""
        zone = self._zone(zone)
        response = self.client.put(
            f"{self.collection_path}/{volume_id}:detach",
            zone=zone,
        )
        return self._settle_operation(response, zone=zone, wait=wait)

    def resize(
        self,
        volume_id: str,
        size: int,
        *,
        zone: Optional[str] = None,
        wait: Optional[bool] = None,
    ) -> Operation:
        """Resize a volume to ``size`` GiB (async, size can only increase).

        Uses the dedicated colon-action endpoint
        ``PUT /block-storage/{id}:resize-volume``.

        Unit caveat: the OpenAPI spec documents the wire ``size`` field as GiB,
        but the live API actually expects **bytes** (verified empirically). We
        keep the caller-facing parameter in GiB — matching ``create`` and the
        ``get`` response — and convert to bytes for the wire format.
        """
        zone = self._zone(zone)
        # 1 GiB == 1024**3 bytes. Convert here so callers keep using GiB.
        size_bytes = int(size) * 1024 * 1024 * 1024
        response = self.client.put(
            f"{self.collection_path}/{volume_id}:resize-volume",
            zone=zone,
            json={"size": size_bytes},
        )
        return self._settle_operation(response, zone=zone, wait=wait)

    def create_snapshot(
        self,
        volume_id: str,
        payload: object = None,
        *,
        zone: Optional[str] = None,
        wait: Optional[bool] = None,
    ) -> Operation:
        """Trigger a snapshot of this volume via the instance-action endpoint.

        Calls ``POST /block-storage/{volume_id}:create-snapshot`` (async). The
        return value is the settled operation; use
        :class:`~exoscale_connector.resources.block_volume_snapshot.BlockVolumeSnapshotClient`
        to fetch the resulting snapshot by its reference id.
        """
        zone = self._zone(zone)
        response = self.client.post(
            f"{self.collection_path}/{volume_id}:create-snapshot",
            zone=zone,
            json=to_api_payload(payload) if payload is not None else None,
        )
        return self._settle_operation(response, zone=zone, wait=wait)

    # ------------------------------------------------------------------ #
    # Internal helpers
    # ------------------------------------------------------------------ #
    def _settle_operation(
        self,
        response: dict,
        *,
        zone: Optional[str],
        wait: Optional[bool],
    ) -> Operation:
        """Parse an operation envelope and await completion if configured to do so."""
        operation = Operation.model_validate(response)
        if self._should_wait(wait) and operation.id:
            operation = self.client.wait_operation(operation, zone=zone)
        return operation
