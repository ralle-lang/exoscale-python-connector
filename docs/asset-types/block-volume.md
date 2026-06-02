# block-volume

Persistent block storage that can be attached to a single compute instance
at a time. Created in a zone, attached/detached online, resizable upward
only — and **only while attached to a running instance**. Volumes are
encrypted at rest by default.

## Model

```python
class BlockVolumeSnapshotRef(ExoscaleModel):
    id: Optional[str]
    name: Optional[str]


class BlockVolume(ExoscaleModel):
    id: Optional[str]
    name: Optional[str]
    description: Optional[str]
    size: Optional[int]                          # GiB (on get); see resize gotcha
    state: Optional[str]                         # "detached" | "attached"
    created_at: Optional[str]
    blocksize: Optional[int]                     # typically 4096
    labels: Optional[Dict[str, str]]
    instance: Optional[Reference]                # the attached instance, when state == "attached"
    snapshots: Optional[List[BlockVolumeSnapshotRef]]
```

## CLI

```bash
exoscale-block-volume list
exoscale-block-volume get --id <uuid>
exoscale-block-volume find --name <name>
exoscale-block-volume create --json '{"name": "data", "size": 10}'
exoscale-block-volume delete --id <uuid>
```

> attach / detach / resize / create-snapshot are exposed via the library
> client (and a future CLI update can add subcommands for them).

## Library

```python
from exoscale_connector import ExoscaleClient
from exoscale_connector.resources.block_volume import BlockVolumeClient

volumes = BlockVolumeClient(ExoscaleClient.from_env(zone="de-fra-1"))

# Create (size in GiB)
vol = volumes.create({"name": "data", "size": 10})

# Online ops — these require the volume to be attached to a running instance
volumes.attach(vol.id, instance_id)
volumes.resize(vol.id, 20)       # GiB; see gotcha
op = volumes.create_snapshot(vol.id)   # snapshot id is op.reference_id
volumes.detach(vol.id)

volumes.delete(vol.id)
```

## Gotchas

- **`list_key` is `block-storage-volumes`, NOT `block-storages`.** Caught
  by the Tier 2 live test (commit `65afd51`); originally wrong.
- **`resize` endpoint is `:resize-volume`**, not `:resize` and not the plain
  `PUT /block-storage/{id}` (which accepts the size field on the wire but
  silently drops it). Connector fixed in commit `41d1f23`.
- **Resize `size` is in BYTES on the wire**, despite the OpenAPI spec
  documenting GiB. The connector takes GiB from callers and converts to
  bytes internally so the caller-facing unit stays consistent with `create`
  and `get`.
- **Resize is online-only**: the volume must be attached to a running
  instance for the size change to propagate. A resize on a detached
  volume returns a success-looking response but the size never changes.
- **Resize only grows**: can't shrink a volume.
- **Attach requires `standard.small` or larger** — `standard.tiny` is
  rejected with `409: Instance size must be at least small`.
- **Delete fails (412) if attached**: detach first. The Tier 3 test wraps
  the tracker deleter in a safe-delete helper that detaches first if the
  volume is still attached when teardown runs.
- **Volume → tenant quota**: many accounts have a low total
  block-storage quota. Plan capacity before running tests that resize.

## End-to-end example

Distilled from
[`tests/integration/test_tier_2.py::test_block_volume_lifecycle`](../../tests/integration/test_tier_2.py)
(detached) and
[`tests/integration/test_tier_3.py::test_block_volume_online_lifecycle`](../../tests/integration/test_tier_3.py)
(online ops):

```python
from exoscale_connector import ExoscaleClient
from exoscale_connector.resources.block_volume import BlockVolumeClient
from exoscale_connector.resources.block_volume_snapshot import BlockVolumeSnapshotClient

client = ExoscaleClient.from_env(zone="de-fra-1")
volumes = BlockVolumeClient(client)
snapshots = BlockVolumeSnapshotClient(client)

# 1. Create (smallest is 10 GiB)
vol = volumes.create({"name": "data", "size": 10})
assert volumes.get(vol.id).state == "detached"

# 2. Snapshot (no attached instance required for snapshot)
op = volumes.create_snapshot(vol.id)
snap_id = op.reference_id

# 3. Online operations need an attached instance (size >= standard.small)
volumes.attach(vol.id, instance_id)
volumes.resize(vol.id, 20)         # GiB; wait+poll for vol.size to change
volumes.detach(vol.id)

# 4. Cleanup
snapshots.delete(snap_id)
volumes.delete(vol.id)
```
