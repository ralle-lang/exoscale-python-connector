# iam-user

An organisation user — a human member of the account. Identified by email.
**Mutation is intentionally not exercised by the live test suite** because
creating a user sends an invite email to a real address; the connector
exposes the endpoints but the live-test harness only does read-only
operations on existing users.

## Model

```python
class IAMUser(ExoscaleModel):
    id: Optional[str]
    email: Optional[str]      # the unique human identifier
    role_id: Optional[str]    # bound role
    role: Optional[Reference]
    pending: Optional[bool]   # True until the invitation is accepted
```

## CLI

```bash
exoscale-iam-user list
exoscale-iam-user get --id <uuid>
exoscale-iam-user find --name some.user@example.com   # name_field="email"
# create / delete are exposed but trigger real invite emails — use with care.
```

## Library

```python
from exoscale_connector import ExoscaleClient
from exoscale_connector.resources.iam_user import IAMUserClient

users = IAMUserClient(ExoscaleClient.from_env(zone="de-fra-1"))

for user in users.list():
    print(user.id, user.email)

found = users.find_by_name("alice@example.com")  # name_field="email"
```

## Gotchas

- **`find_by_name` matches `email`**, not a separate `name` field — the
  client sets `name_field = "email"` because users have no other label.
- **There is no `GET /user/{id}`.** The API 404s on it even for existing
  users (verified live 2026-10-07). `get()` therefore lists `/user` and
  matches by id — one list call per lookup — and the re-fetch after
  `create()` / `update()` goes through the same path. A freshly invited user
  is listed with `pending: true`.
- **`create` triggers an email side-effect.** Calling `users.create({...})`
  with an unverified address will either bounce or spam someone — do not
  call from automated tests. The connector keeps the method available for
  legitimate provisioning workflows.

## End-to-end example (read-only)

```python
from exoscale_connector import ExoscaleClient
from exoscale_connector.resources.iam_user import IAMUserClient

users = IAMUserClient(ExoscaleClient.from_env(zone="de-fra-1"))

# Inventory existing org users — safe in any environment.
for u in users.list():
    print(u.email, "->", u.role_id)
```
