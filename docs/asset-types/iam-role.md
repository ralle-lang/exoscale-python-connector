# iam-role

An IAM role bundles a set of permissions plus an optional inline policy. API
keys are bound to a role at creation time; the role determines what the key
can do. Account-global.

> Building a policy? See the **[IAM policy cookbook](../iam-policy-cookbook.md)**
> for ready-made helpers (`IAMPolicy.allow_services([...])`, …) and recipes.

## Model

```python
class IAMPolicyRule(ExoscaleModel):
    action: Optional[str]                      # "allow" | "deny"
    expression: Optional[str]                  # Exoscale IAM DSL, kept verbatim
    resources: Optional[List[str]]


class IAMPolicyService(ExoscaleModel):
    type: Optional[str]                        # "allow" | "deny" | "rules"
    rules: Optional[List[IAMPolicyRule]]       # used when type == "rules"


class IAMPolicy(ExoscaleModel):
    default_service_strategy: Optional[str]    # "allow" | "deny"
    services: Optional[Dict[str, IAMPolicyService]]   # keyed by service name


class IAMRole(ExoscaleModel):
    id: Optional[str]
    name: Optional[str]
    description: Optional[str]
    editable: Optional[bool]
    permissions: Optional[List[str]]
    labels: Optional[Dict[str, str]]
    policy: Optional[IAMPolicy]               # permission policy
    assume_role_policy: Optional[IAMAssumeRolePolicy]  # {rules: [...]}: who/what may assume the role
```

> Inline `policy` / `assume_role_policy` work on **create**. To change them on an
> existing role, use `IAMRoleClient.set_policy(role_id, policy)` /
> `set_assume_role_policy(role_id, policy)`. Under the hood the two are
> asymmetric: `policy` has a dedicated `PUT :policy` sub-endpoint, while
> `assume-role-policy` travels in the generic `PUT /iam-role/{id}` body — the
> setters hide this. See the
> [IAM policy cookbook](../iam-policy-cookbook.md).

## CLI

```bash
exoscale-iam-role list
exoscale-iam-role get --id <uuid>
exoscale-iam-role find --name <name>
exoscale-iam-role create --json '{"name": "read-only", "description": "list+get only", "policy": {"default-service-strategy": "deny", "services": {}}}'
exoscale-iam-role delete --id <uuid>
```

## Library

```python
from exoscale_connector import ExoscaleClient
from exoscale_connector.resources.iam_role import IAMPolicy, IAMRole, IAMRoleClient

roles = IAMRoleClient(ExoscaleClient.from_env(zone="de-fra-1"))

role = roles.create(IAMRole(
    name="read-only",
    description="list+get only",
    policy=IAMPolicy(default_service_strategy="deny", services={}),
))

roles.update(role.id, {"description": "list+get only (updated)"})
roles.delete(role.id)
```

A rule-based policy (deny everything except TXT records under one domain):

```python
from exoscale_connector.resources.iam_role import (
    IAMPolicy, IAMPolicyRule, IAMPolicyService, IAMRole,
)

role = roles.create(IAMRole(
    name="acme-dns",
    policy=IAMPolicy(
        default_service_strategy="deny",
        services={
            "dns": IAMPolicyService(
                type="rules",
                rules=[
                    IAMPolicyRule(action="deny", expression="parameters.has('type') && parameters.type != 'TXT'"),
                    IAMPolicyRule(action="allow", expression="operation in ['create-dns-domain-record', 'delete-dns-domain-record']"),
                ],
            ),
        },
    ),
))
```

## Organization policy

One `IAMPolicy` that applies to every API key in the organization, evaluated
in addition to each key's role policy. It uses the same models and builders as
role policies. Implemented from the API reference — pending live verification.

```python
current = roles.get_organization_policy()          # IAMPolicy

# Replace it (awaits the operation unless wait=False). A too-strict policy can
# lock out the very key making the call, so start from `current`.
roles.set_organization_policy(current)

# Back to the default, discarding every customisation org-wide. Refuses to
# run without confirm=True.
roles.reset_organization_policy(confirm=True)
```

- None of the three is on the CLI: an org-wide write is too easy to fire by
  accident from a shell, so it stays a deliberate library call.
- The live tests only ever read the organization policy.

## Gotchas

- **The policy envelope is typed; rule expressions are not.** `services`,
  per-service `type`, and the `rules` list (`action` / `expression` /
  `resources`) are modelled, but `expression` stays a free-form string — it is
  Exoscale's CEL-like condition language (e.g.
  `resources.bucket != "backups"`, `operation in ['list-dns-domains']`) and the
  connector never parses it. See Exoscale's
  [IAM policy guide](https://community.exoscale.com/product/iam/how-to/policy-guide/)
  for the expression syntax.
- **`services` is an open map.** Service names (`compute`, `dns`, `sos`, …) are
  not enumerated, and `extra="allow"` preserves any field the API adds, so the
  model keeps round-tripping unknown content losslessly.
- **`editable=false` roles are managed by Exoscale** (e.g. the built-in
  admin role) and cannot be modified or deleted; the API will reject the
  attempt with a 403/409.
- **There is no `:assume-role-policy` sub-endpoint.** The API reference's
  symmetry suggests one, but `PUT /iam-role/{id}:assume-role-policy` returns
  **404** — confirmed live (2026-06-10). Assume-role-policy changes go through
  the generic `PUT /iam-role/{id}` body instead (`{"assume-role-policy": ...}`),
  which is what `set_assume_role_policy()` does. Only the permission `policy`
  has a dedicated sub-endpoint (`PUT :policy`).
- **The assume-role policy is a flat rule list, not a permission policy.** Its
  spec shape is `{"rules": [{"action", "expression", "resources"}]}` —
  build it with `IAMAssumeRolePolicy.with_rules(IAMPolicyRule.allow(...))`.
  Earlier releases typed it as `IAMPolicy`
  (`default-service-strategy` / `services`), which the API does not define.
- **Does `get()` echo `assume-role-policy`?** Live runs saw it come back as
  `None` on ordinary roles, but those runs sent the old `IAMPolicy` shape, so
  the API may simply have ignored the body. Re-verify with the spec shape
  before relying on either behaviour. The permission `policy` does round-trip
  on `get()`.

## End-to-end example

Distilled from
[`tests/integration/test_tier_1.py::test_iam_role_lifecycle`](../../tests/integration/test_tier_1.py):

```python
from exoscale_connector import ExoscaleClient
from exoscale_connector.resources.iam_role import IAMPolicy, IAMRole, IAMRoleClient

roles = IAMRoleClient(ExoscaleClient.from_env(zone="de-fra-1"))

# Create a deny-all role (harmless even if its key leaks).
role = roles.create(IAMRole(
    name="connector-smoke",
    description="tier-1 smoke",
    policy=IAMPolicy(default_service_strategy="deny", services={}),
))

assert roles.get(role.id).name == "connector-smoke"
roles.update(role.id, {"description": "updated"})
assert roles.get(role.id).description == "updated"
roles.delete(role.id)
```
