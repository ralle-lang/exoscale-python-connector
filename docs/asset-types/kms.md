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

All 16 `/kms-key` endpoints were verified live on 2026-11-02; see
[live test results](../live-test-results.md). API keys need the IAM `kms`
service.

## Model

```python
class KeyRotationConfig(ExoscaleModel):
    automatic: Optional[bool]
    manual_count: Optional[int]
    next_at: Optional[str]
    rotation_period: Optional[int]     # days; 0 while automatic rotation is off


class KmsKey(ExoscaleModel):
    id: Optional[str]
    name: Optional[str]
    description: Optional[str]
    status: Optional[str]              # "enabled" | "disabled" | "pending-deletion"
    status_since: Optional[str]
    delete_at: Optional[str]           # set once a deletion is scheduled
    usage: Optional[str]               # "encrypt-decrypt"
    key_spec: Optional[str]            # returned live, not in the spec
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
exoscale-kms disable-rotation --id <uuid>              # new keys already rotate yearly
exoscale-kms enable-rotation --id <uuid> --period 90
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

# Rotation: new keys already rotate every 365 days. To change the period,
# disable first — enabling while automatic rotation is on is a 400.
kms.disable_rotation(key.id)
kms.enable_rotation(key.id, rotation_period=90)   # 90–2560 days
kms.rotate(key.id)
rotations = kms.list_rotations(key.id)

# Envelope crypto (secret-bearing — never log/print the results).
# plaintext and ciphertext are Base64-encoded.
enc = kms.encrypt(key.id, plaintext_b64)
dec = kms.decrypt(key.id, enc["ciphertext"])
assert dec["plaintext"] == plaintext_b64

# Re-encrypt, e.g. to drop or change the encryption context
new = kms.re_encrypt(
    key.id,
    source={"key": key.id, "ciphertext": enc["ciphertext"]},
    destination={"key": key.id},
)

# Data key: use the plaintext, store only the ciphertext.
dk = kms.generate_data_key(key.id)                 # AES-256 (32 bytes)
dk16 = kms.generate_data_key(key.id, bytes_count=16)
# dk["plaintext"] -> use then discard;  dk["ciphertext"] -> persist

# Deletion lifecycle (no immediate delete)
kms.schedule_deletion(key.id, delay_days=7)   # 7–30 days -> {"delete-at": ...}
kms.cancel_deletion(key.id)                    # abort while pending; key is now disabled
kms.enable(key.id)                             # ...so re-enable it
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
  `replicate(key_id, to_zone)`; `replicas` lists where it currently lives. The
  first call answers `{"status": "target-registered"}` and completes in the
  background: the replica is briefly not found in the target zone. It then
  mirrors the origin key's status with a short lag. Operations issued against
  the replica (e.g. `schedule_deletion` in its zone) fail with 400 "Operation
  not allowed on replica"; schedule the origin key and the replica follows.
- **Automatic rotation is on by default.** A new key rotates every 365 days.
  `enable_rotation` while it is on fails with 400 "Duplicate rotation call not
  allowed"; call `disable_rotation` first, then `enable_rotation` with the new
  period (90–2560 days, default 365). While off, the rotation config reports
  `rotation_period` 0 and a zero-time `next_at`.
- **`cancel_deletion` leaves the key disabled.** A key in `pending-deletion`
  can't encrypt ("Key is disabled"), and cancelling restores it to `disabled`,
  not `enabled` — call `enable()` afterwards. `delay_days` must be 7–30.
- **Data key size: `key_spec` or `bytes_count`, not both.** The API rejects the
  combination; the client raises `ValueError`. With neither, it asks for
  `AES-256`.
- **`re_encrypt` needs the key id in both envelopes.** `source` takes `key`,
  `ciphertext` and the original `encryption-context` if one was used;
  `destination` takes `key` and an optional new context.
- **Crypto responses carry extra algorithm fields.** `encrypt`/`decrypt` add
  `encryption-algorithm`, and `re_encrypt` adds `source-`/`destination-encryption-algorithm`,
  alongside the documented `ciphertext`/`plaintext`.
- **Synchronous, so `wait=` is irrelevant** — every call returns its result
  immediately, unlike the async asset types.
