# kms (Key Management Service)

Exoscale-managed encryption keys (`/kms-key`): lifecycle (create / enable /
disable), rotation, envelope crypto (encrypt / decrypt / re-encrypt /
generate-data-key), a deferred deletion lifecycle, and cross-zone replication.

Two things set KMS apart:

- **No immediate delete.** There is no `DELETE /kms-key/{id}`. A key is removed
  by *scheduling* a deletion (a cancellable waiting period). `delete()` raises;
  use `schedule_deletion()` / `cancel_deletion()`.
- **Synchronous.** KMS endpoints return their result directly — no async
  operation envelopes to wait on.

## Model

```python
class KeyRotationConfig(ExoscaleModel):
    automatic: Optional[bool]
    manual_count: Optional[int]
    next_at: Optional[str]
    rotation_period: Optional[int]     # days


class KmsKey(ExoscaleModel):
    id: Optional[str]
    name: Optional[str]
    description: Optional[str]
    status: Optional[str]              # "enabled" | "disabled" | "pending-deletion"
    status_since: Optional[str]
    delete_at: Optional[str]           # set once a deletion is scheduled
    usage: Optional[str]               # "encrypt-decrypt"
    source: Optional[str]              # "exoscale-kms"
    multi_zone: Optional[bool]
    origin_zone: Optional[str]
    material: Optional[Dict[str, Any]]           # key material metadata (passthrough)
    revision: Optional[Dict[str, Any]]           # revision stamp (passthrough)
    rotation: Optional[KeyRotationConfig]
    replicas: Optional[List[str]]                # zones this key is replicated to
    replicas_status: Optional[List[Dict[str, Any]]]
    created_at: Optional[str]
```

## CLI

Management verbs only. The **crypto operations are intentionally not on the
CLI** — they take/return secret material and CLI arguments leak into the process
list; use the library for those.

```bash
exoscale-kms list
exoscale-kms get --id <uuid>
exoscale-kms create --json '{"name": "app-key", "usage": "encrypt-decrypt", "multi-zone": true}'
exoscale-kms enable --id <uuid>
exoscale-kms disable --id <uuid>
exoscale-kms rotate --id <uuid>
exoscale-kms enable-rotation --id <uuid> --period 90
exoscale-kms disable-rotation --id <uuid>
exoscale-kms list-rotations --id <uuid>
exoscale-kms schedule-deletion --id <uuid> --delay-days 7
exoscale-kms cancel-deletion --id <uuid>
exoscale-kms replicate --id <uuid> --to-zone at-vie-1
```

## Library

```python
from exoscale_connector import ExoscaleClient
from exoscale_connector.resources.kms import KmsKeyClient

kms = KmsKeyClient(ExoscaleClient.from_env(zone="de-fra-1"))

# Create + inspect (create returns the key directly — KMS is synchronous)
key = kms.create({"name": "app-key", "usage": "encrypt-decrypt"})
fetched = kms.get(key.id)

# Rotation
kms.enable_rotation(key.id, rotation_period=90)
kms.rotate(key.id)
rotations = kms.list_rotations(key.id)

# Envelope crypto (secret-bearing — never log/print the results).
# plaintext and ciphertext are Base64-encoded.
enc = kms.encrypt(key.id, plaintext_b64)
dec = kms.decrypt(key.id, enc["ciphertext"])
assert dec["plaintext"] == plaintext_b64

# Data key: use the plaintext, store only the ciphertext.
dk = kms.generate_data_key(key.id, key_spec="AES-256")
# dk["plaintext"] -> use then discard;  dk["ciphertext"] -> persist

# Deletion lifecycle (no immediate delete)
kms.schedule_deletion(key.id, delay_days=7)   # -> {"delete-at": ...}
kms.cancel_deletion(key.id)                    # abort while pending
```

## Gotchas

- **No `delete()`.** It raises `NotImplementedError`. Keys are removed via
  `schedule_deletion()` (moves the key to `pending-deletion` for a cancellable
  waiting window); `cancel_deletion()` restores it before the window elapses.
- **Crypto is library-only and secret-bearing.** `encrypt`/`decrypt`/
  `re_encrypt`/`generate_data_key` are never exposed on the CLI. Their
  `plaintext` / data-key values are secrets — never log, print, or persist them.
  Store only the `ciphertext`.
- **Base64 in, Base64 out.** `plaintext`, `ciphertext`, and `encryption_context`
  are Base64-encoded strings on the wire; encode/decode at your boundary.
- **`encryption_context` must match.** If you pass one to `encrypt`, you must
  pass the identical context to `decrypt`.
- **Replication needs a multi-zone key.** Create with `"multi-zone": true`, then
  `replicate(key_id, to_zone)`; `replicas` lists where it currently lives.
- **Synchronous, so `wait=` is irrelevant** — every call returns its result
  immediately, unlike the async asset types.
