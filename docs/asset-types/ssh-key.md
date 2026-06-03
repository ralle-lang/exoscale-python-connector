# ssh-key

An ssh public key registered with the account, used when creating instances
so that the matching private key can SSH in. Account-global (not zone-scoped)
but reached through any zone host. **Identified by name, not UUID** — its
name *is* its id in the URL path.

## Model

```python
class SSHKey(ExoscaleModel):
    name: Optional[str]         # the unique identifier (used in URL paths)
    fingerprint: Optional[str]  # MD5 / SHA fingerprint computed by the API
    public_key: Optional[str]   # OpenSSH-format public key, write-only on get
```

## CLI

```bash
exoscale-ssh-key list
exoscale-ssh-key get --id laptop                  # name is the id
exoscale-ssh-key find --name laptop
exoscale-ssh-key create --json '{"name": "laptop", "public-key": "ssh-ed25519 AAAAC3... user@host"}'
exoscale-ssh-key delete --id laptop
```

## Library

```python
from exoscale_connector import ExoscaleClient
from exoscale_connector.resources.ssh_key import SSHKey, SSHKeyClient

keys = SSHKeyClient(ExoscaleClient.from_env(zone="de-fra-1"))

# Register
key = keys.create(SSHKey(name="laptop", public_key="ssh-ed25519 AAAAC3... user@host"))

# Fetch by name (which is the id)
fetched = keys.get("laptop")
print(fetched.fingerprint)

# Remove
keys.delete("laptop")
```

## Gotchas

- **Name is the id.** `keys.get("laptop")` calls `GET /ssh-key/laptop`, not
  `GET /ssh-key/<uuid>`. `id_field` / `name_field` are both `"name"` on this
  client.
- **No `update` endpoint.** Keys are immutable — to rotate, delete and
  recreate. The connector intentionally exposes no `update`.
- **Public key format.** Send the OpenSSH single-line form
  (`"ssh-ed25519 AAAA... optional comment"`). The API computes the
  fingerprint and returns it on subsequent `get` responses; `public_key`
  itself is often omitted from listing responses.
- **Async-but-no-reference quirk.** The create response is an operation
  envelope with no `reference` field — the connector handles this by
  re-fetching via the submitted name (for name-keyed resources, the id *is*
  the submitted name). Caught by the Tier 1 live test.

## End-to-end example

Distilled from
[`tests/integration/test_tier_1.py::test_ssh_key_lifecycle`](../../tests/integration/test_tier_1.py):

```python
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from exoscale_connector import ExoscaleClient
from exoscale_connector.resources.ssh_key import SSHKey, SSHKeyClient

# Generate an ephemeral keypair in-memory (private key is discarded).
private = Ed25519PrivateKey.generate()
pub = private.public_key().public_bytes(
    Encoding.OpenSSH, PublicFormat.OpenSSH
).decode("ascii")

keys = SSHKeyClient(ExoscaleClient.from_env(zone="de-fra-1"))
keys.create(SSHKey(name="laptop", public_key=f"{pub} demo"))
assert keys.get("laptop").fingerprint
keys.delete("laptop")
```
