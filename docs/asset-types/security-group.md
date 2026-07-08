# security-group (+ rules)

A security group is an Exoscale L3/L4 firewall ruleset that you attach to
compute resources (instances, instance pools, SKS nodepools). It owns its
ingress / egress rules as sub-resources.

## Model

```python
class SecurityGroupResource(ExoscaleModel):
    id: Optional[str]               # target SG uuid
    name: Optional[str]
    visibility: Optional[str]       # "private" (your account) | "public" (Exoscale-managed)


class SecurityGroupRule(ExoscaleModel):
    id: Optional[str]               # API-assigned uuid
    description: Optional[str]      # free-form, useful as a human-friendly tag
    flow_direction: Optional[str]   # "ingress" | "egress"
    protocol: Optional[str]         # "tcp" | "udp" | "icmp" | "icmpv6"
    start_port: Optional[int]
    end_port: Optional[int]
    network: Optional[str]          # CIDR — mutually exclusive with security_group
    security_group: Optional[SecurityGroupResource]  # peer/public SG source or dest


class SecurityGroup(ExoscaleModel):
    id: Optional[str]
    name: Optional[str]             # the human-readable identifier
    description: Optional[str]
    rules: List[SecurityGroupRule]  # embedded on every detail response
    external_sources: Optional[List[str]]  # IP set names (Exoscale-managed allow/deny lists)
```

## CLI

```bash
exoscale-security-group list
exoscale-security-group get --id <uuid>
exoscale-security-group find --name <name>
exoscale-security-group create --json '{"name": "web", "description": "public web tier"}'
exoscale-security-group delete --id <uuid>
```

> Rule management is exposed via the library client (`add_rule` / `delete_rule`).
> A future CLI update can add `rule-add`/`rule-delete` subcommands.

## Library

```python
from exoscale_connector import ExoscaleClient
from exoscale_connector.resources.security_group import (
    SecurityGroupClient, SecurityGroupRule,
)

client = ExoscaleClient.from_env(zone="de-fra-1")
sg = SecurityGroupClient(client)

# CRUD
group = sg.create({"name": "web", "description": "public web tier"})
fetched = sg.get(group.id)
maybe = sg.find_by_name("web")  # -> SecurityGroup | None
sg.delete(group.id)

# Rule add / delete
sg.add_rule(group.id, SecurityGroupRule(
    flow_direction="ingress",
    protocol="tcp",
    start_port=443,
    end_port=443,
    network="0.0.0.0/0",
    description="https-from-anywhere",
))
sg.delete_rule(group.id, rule_id)
```

## Gotchas

- **Rules are not addressable by name.** Always carry an explicit
  `description` if you need to find rules later — `find` only works on the
  parent group's `name`.
- **Cannot delete a security group while it is referenced** by a running
  instance, instance pool, or LB. The API returns 412 — detach first.
- **Adding a rule is async**; the operation completes within a few seconds
  but `wait=False` is available for fire-and-forget scenarios.
- **Peer-SG rules take a typed `security_group` reference, not a CIDR.** A rule
  can allow traffic from another security group's members instead of a
  `network` CIDR — the two are mutually exclusive. Reference a **private** peer
  in your own account by id (`{"security-group": {"id": "<uuid>"}}`), and an
  Exoscale-managed **public** group by adding `"visibility": "public"`
  (`{"security-group": {"id": "<uuid>", "visibility": "public"}}`). Both round-trip
  on the response as a `SecurityGroupResource`.

## End-to-end example

Distilled from
[`tests/integration/test_tier_1.py::test_security_group_lifecycle`](../../tests/integration/test_tier_1.py):

```python
from exoscale_connector import ExoscaleClient
from exoscale_connector.resources.security_group import (
    SecurityGroupClient, SecurityGroupRule,
)

client = ExoscaleClient.from_env(zone="de-fra-1")
sg = SecurityGroupClient(client)

# 1. Create
group = sg.create({"name": "web", "description": "tier-1 smoke"})
sg_id = group.id

# 2. Verify
assert sg.get(sg_id).name == "web"
assert sg.find_by_name("web").id == sg_id

# 3. Add a rule
sg.add_rule(sg_id, SecurityGroupRule(
    flow_direction="ingress", protocol="tcp",
    start_port=443, end_port=443, network="0.0.0.0/0",
    description="https",
))

# 4. Verify the rule is present
refreshed = sg.get(sg_id)
assert any(r.description == "https" for r in refreshed.rules)

# 5. Cleanup
for r in refreshed.rules:
    if r.description == "https":
        sg.delete_rule(sg_id, r.id)
sg.delete(sg_id)
```
