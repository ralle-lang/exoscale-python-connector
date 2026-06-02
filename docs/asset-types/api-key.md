# api-key

A scoped credential bound to an IAM role at creation time. The role
determines what the key can do; the key's name/identifier on the wire is
its **key id** (an API-generated string), and the **secret is returned
exactly once** on the create response — there is no way to re-fetch it.

## Model

```python
class ApiKey(ExoscaleModel):
    key: Optional[str]        # API key id (the public part, used in URL paths)
    name: Optional[str]
    role_id: Optional[str]    # bound role's id
    role: Optional[Reference]
    secret: Optional[str]     # PRESENT ONLY ON CREATE — never returned later
```

## CLI

```bash
exoscale-api-key list
exoscale-api-key get --id <key-id>
exoscale-api-key find --name <name>
exoscale-api-key create --json '{"name": "ci-bot", "role-id": "<role-uuid>"}'
exoscale-api-key delete --id <key-id>
```

## Library

```python
from exoscale_connector import ExoscaleClient
from exoscale_connector.resources.api_key import ApiKeyClient

keys = ApiKeyClient(ExoscaleClient.from_env(zone="de-fra-1"))

created = keys.create({"name": "ci-bot", "role-id": "<role-uuid>"})
# Capture the secret IMMEDIATELY — it is not retrievable later.
secret = created.secret
key_id = created.key

# Listing / fetching never returns the secret.
for existing in keys.list():
    print(existing.key, existing.name)

keys.delete(key_id)
```

## Gotchas

- **`secret` is one-shot.** The first response after `create` is the only
  time the secret is visible. Persist it to a vault immediately; never log it.
- **`id_field = "key"`** — the path token is the `key` field, not a uuid in
  `id`. `keys.get("EXO...")` calls `GET /api-key/EXO...`.
- **`update` not exposed.** The API does not allow rotating a key in place —
  delete and create a new one.
- **Tier 1 live test for create is gated separately** (off by default) so
  the standard Tier 1 run never produces a stray secret-bearing response.
  Enable with `EXOSCALE_TEST_TIER_1_API_KEY=1`.

## End-to-end example

```python
from exoscale_connector import ExoscaleClient
from exoscale_connector.resources.api_key import ApiKeyClient
from exoscale_connector.resources.iam_role import IAMPolicy, IAMRole, IAMRoleClient

client = ExoscaleClient.from_env(zone="de-fra-1")
roles = IAMRoleClient(client)
keys = ApiKeyClient(client)

# Bind to a minimal role created just for this key.
role = roles.create(IAMRole(
    name="ci-bot-role",
    policy=IAMPolicy(default_service_strategy="deny", services={}),
))

created = keys.create({"name": "ci-bot", "role-id": role.id})
assert created.secret, "secret must be returned exactly once"
# Hand `created.key` / `created.secret` to your vault here.

# Teardown
keys.delete(created.key)
roles.delete(role.id)
```
