# IAM policy cookbook

Exoscale IAM is powerful but easy to get lost in. This connector splits the
problem in two:

- **The policy structure** — which services, allow/deny/rules, the skeleton — is
  fully typed and comes with helper constructors. You rarely need to assemble it
  by hand.
- **The rule expressions** — strings such as `resources.bucket != "backups"` —
  are Exoscale's own condition language (a CEL-like DSL). The connector keeps
  them verbatim and never parses them. To write expressions, see Exoscale's
  [IAM policy guide](https://community.exoscale.com/product/iam/how-to/policy-guide/).

Everything below imports from one module:

```python
from exoscale_connector.resources.iam_role import (
    IAMPolicy, IAMPolicyService, IAMPolicyRule,
    RuleAction, ServiceType, ServiceStrategy,   # optional enums, for autocomplete
    IAMRole, IAMRoleClient,
)
```

## Quick reference

| Helper | Builds |
|---|---|
| `IAMPolicy.deny_all()` | default-deny, no exceptions |
| `IAMPolicy.allow_all()` | default-allow, no exceptions |
| `IAMPolicy.allow_services([...])` | default-deny, blanket-allow the listed services |
| `IAMPolicyService.allow()` / `.deny()` | a blanket decision for one service |
| `IAMPolicyService.with_rules(rule, ...)` | a `type: rules` block, evaluated top-to-bottom |
| `IAMPolicyRule.allow(expr)` / `.deny(expr)` | one rule (optionally `resources=[...]`) |

The enums (`RuleAction`, `ServiceType`, `ServiceStrategy`) are an optional
convenience — they subclass `str`, so `RuleAction.ALLOW` and `"allow"` are
interchangeable. The model fields stay plain strings, so you can always pass a
value Exoscale adds later.

## Recipes

### Deny everything (safe default)

Good for a key that should not act yet, or as a base you tighten later.

```python
policy = IAMPolicy.deny_all()
```

### Allow everything (use sparingly)

```python
policy = IAMPolicy.allow_all()
```

### Allow only specific services

Default-deny, then fully allow the named services (service names are open — use
whatever Exoscale documents, e.g. `compute`, `dns`, `dbaas`, `sos`, `iam`).

```python
policy = IAMPolicy.allow_services(["compute", "dns"])
```

### Restrict to a single Object Storage bucket

The "first matching rule wins" pattern: deny anything that is not the target
bucket, then allow the rest.

```python
policy = IAMPolicy(
    default_service_strategy=ServiceStrategy.DENY,
    services={
        "sos": IAMPolicyService.with_rules(
            IAMPolicyRule.deny('resources.bucket != "backups"'),
            IAMPolicyRule.allow("true"),
        ),
    },
)
```

### ACME DNS-01 (only TXT records under `_acme-challenge`)

A cert-manager-style key that may only manage ACME challenge records.

```python
policy = IAMPolicy(
    default_service_strategy=ServiceStrategy.DENY,
    services={
        "dns": IAMPolicyService.with_rules(
            IAMPolicyRule.deny("parameters.has('type') && parameters.type != 'TXT'"),
            IAMPolicyRule.deny("parameters.has('name') && !parameters.name.startsWith('_acme-challenge')"),
            IAMPolicyRule.allow(
                "operation in ['list-dns-domains', 'list-dns-domain-records', "
                "'create-dns-domain-record', 'delete-dns-domain-record']"
            ),
        ),
    },
)
```

### Limit a service to specific operations

```python
policy = IAMPolicy(
    default_service_strategy=ServiceStrategy.DENY,
    services={
        "compute": IAMPolicyService.with_rules(
            IAMPolicyRule.allow("operation in ['list-instances', 'get-instance']"),
        ),
    },
)
```

## Attaching a policy to a role

```python
roles = IAMRoleClient(ExoscaleClient.from_env(zone="de-fra-1"))

role = roles.create(IAMRole(
    name="acme-dns",
    description="cert-manager DNS-01 only",
    policy=policy,
))
```

## Updating the policy on an existing role

Policy changes on an existing role go through dedicated sub-endpoints — the
generic `update()` only changes the role's own attributes (name, description,
permissions, labels). Use `set_policy` / `set_assume_role_policy`:

```python
roles.set_policy(role_id, IAMPolicy.allow_services(["compute", "dns"]))
roles.set_assume_role_policy(role_id, IAMPolicy.deny_all())
```

## Inspecting an existing role's policy

Responses parse into the same typed models, so you can walk a policy
programmatically:

```python
role = roles.get(role_id)
if role.policy:
    print(role.policy.default_service_strategy)
    for service, block in (role.policy.services or {}).items():
        if block.type == "rules":
            for rule in block.rules or []:
                print(service, rule.action, rule.expression)
        else:
            print(service, block.type)
```

## Writing expressions

The connector does not validate or generate expression strings — they are
Exoscale's domain. The identifiers you will see most often:

- `operation` — the API operation name, e.g. `operation in ['list-instances']`
- `resources.<field>` — attributes of the target resource, e.g. `resources.bucket`
- `parameters.<field>` — request parameters, with `parameters.has('field')` guards

For the full grammar, operators, and per-service fields, follow Exoscale's
[IAM policy guide](https://community.exoscale.com/product/iam/how-to/policy-guide/).
Because expressions are stored verbatim, anything valid there is valid here.

### Safely interpolating values

When a value comes from outside (a bucket name, a user input), don't build the
expression with an f-string — a stray quote breaks it. The `iam_expr` helpers
quote/escape the *value* for you (they don't validate the full grammar). Field
names — the left-hand side of `eq`/`ne`/`has` — must be developer-written
constants like `"resources.bucket"`; the helpers enforce a dotted-identifier
shape and raise `ValueError` on anything else, so never pass untrusted input
there:

```python
from exoscale_connector import iam_expr as e
from exoscale_connector.resources.iam_role import IAMPolicy, IAMPolicyRule, IAMPolicyService

bucket = user_supplied_name
policy = IAMPolicy(
    default_service_strategy="deny",
    services={
        "sos": IAMPolicyService.with_rules(
            IAMPolicyRule.deny(e.ne("resources.bucket", bucket)),
            IAMPolicyRule.allow("true"),
        ),
    },
)

# Other helpers:
e.eq("resources.bucket", bucket)            # resources.bucket == "<escaped>"
e.has("parameters", "type")                 # parameters.has("type")
e.operation_in(["list-buckets", "get-object"])
e.and_(e.has("parameters", "type"), e.ne("parameters.type", "TXT"))
```
