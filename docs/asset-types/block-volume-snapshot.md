# block-volume-snapshot

A point-in-time snapshot of a block-volume. Created via the parent
volume's `:create-snapshot` action; can be deleted independently, or used
to restore data (recreate the volume from the snapshot).

## Model

```python
class BlockVolumeSnapshot(ExoscaleModel):
    id: Optional[str]
    name: Optional[str]
    size: Optional[int]                   # GiB (matches the source volume size at snapshot time)
    state: Optional[str]                  # "snapshotting" -> "created"
    created_at: Optional[str]
    labels: Optional[Dict[str, str]]
```

## CLI

```bash
exoscale-block-volume-snapshot list
exoscale-block-volume-snapshot get --id <uuid>
exoscale-block-volume-snapshot find --name <name>
exoscale-block-volume-snapshot delete --id <uuid>
```

> Snapshots are created via the parent volume's `create_snapshot` method,
> not via a top-level `create` (the API does not support
> `POST /block-storage-snapshot` directly).

## Library

```python
from exoscale_connector import ExoscaleClient
from exoscale_connector.resources.block_volume import BlockVolumeClient
from exoscale_connector.resources.block_volume_snapshot import (
    BlockVolumeSnapshotClient,
)

client = ExoscaleClient.from_env(zone="de-fra-1")
volumes = BlockVolumeClient(client)
snapshots = BlockVolumeSnapshotClient(client)

# Create via the parent volume
op = volumes.create_snapshot(volume_id)
snap_id = op.reference_id

# Read
snap = snapshots.get(snap_id)
all_snaps = snapshots.list()

# Update / delete
snapshots.update(snap_id, {"labels": {"keep": "yes"}})
snapshots.delete(snap_id)

# Create a NEW volume from this snapshot (use BlockVolumeSnapshotClient.create_from_volume
# on the snapshot client to restore — see the connector source for the exact payload)
```

## Gotchas

- **`list_key` is `block-storage-snapshots`** (the agent got this right;
  the volume one was wrong).
- **Cannot delete the parent volume while snapshots exist** in some account
  configurations — delete snapshots first as a defensive default.
- **Snapshots are point-in-time, not application-consistent**: filesystem
  cache / DB transactions in flight are not flushed by the snapshot itself.
  For consistent backups, quiesce the workload first.

## End-to-end example

Distilled from
[`tests/integration/test_tier_2.py::test_block_volume_lifecycle`](../../tests/integration/test_tier_2.py)
(snapshot covered inside the volume lifecycle):

```python
from exoscale_connector import ExoscaleClient
from exoscale_connector.resources.block_volume import BlockVolumeClient
from exoscale_connector.resources.block_volume_snapshot import (
    BlockVolumeSnapshotClient,
)

client = ExoscaleClient.from_env(zone="de-fra-1")
volumes = BlockVolumeClient(client)
snapshots = BlockVolumeSnapshotClient(client)

vol = volumes.create({"name": "data", "size": 10})

op = volumes.create_snapshot(vol.id)
snap_id = op.reference_id
assert snapshots.get(snap_id).id == snap_id

snapshots.delete(snap_id)
volumes.delete(vol.id)
```
