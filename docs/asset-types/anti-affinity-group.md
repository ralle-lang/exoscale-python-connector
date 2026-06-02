# anti-affinity-group

A scheduling hint telling Exoscale's placement engine that the instances
assigned to this group should be spread across distinct physical hosts. Used
to maximise availability for replica sets (e.g. a 3-node etcd cluster, or an
HA database).

## Model

```python
class AntiAffinityGroup(ExoscaleModel):
    id: Optional[str]
    name: Optional[str]
    description: Optional[str]
    instances: Optional[List[Reference]]   # members; populated on detail responses
```

## CLI

```bash
exoscale-anti-affinity-group list
exoscale-anti-affinity-group get --id <uuid>
exoscale-anti-affinity-group find --name <name>
exoscale-anti-affinity-group create --json '{"name": "etcd-aag", "description": "etcd replica anti-affinity"}'
exoscale-anti-affinity-group delete --id <uuid>
```

## Library

```python
from exoscale_connector import ExoscaleClient
from exoscale_connector.resources.anti_affinity_group import AntiAffinityGroupClient

aag = AntiAffinityGroupClient(ExoscaleClient.from_env(zone="de-fra-1"))

group = aag.create({"name": "etcd-aag", "description": "etcd anti-affinity"})
fetched = aag.get(group.id)
aag.delete(group.id)
```

## Gotchas

- **No `update` endpoint.** The API does not support modifying an AAG in
  place — `update()` is intentionally not exposed on this client. To change
  anything, delete and recreate.
- **Members are read-only here.** Instances are assigned via the
  *instance* create/update endpoint by including the AAG id in the
  instance's `anti-affinity-groups` array.

## End-to-end example

Distilled from
[`tests/integration/test_tier_1.py::test_anti_affinity_group_lifecycle`](../../tests/integration/test_tier_1.py):

```python
from exoscale_connector import ExoscaleClient
from exoscale_connector.resources.anti_affinity_group import AntiAffinityGroupClient

aag = AntiAffinityGroupClient(ExoscaleClient.from_env(zone="de-fra-1"))

group = aag.create({"name": "etcd-aag", "description": "tier-1 smoke"})
assert aag.get(group.id).name == "etcd-aag"
assert aag.find_by_name("etcd-aag").id == group.id
aag.delete(group.id)
```
