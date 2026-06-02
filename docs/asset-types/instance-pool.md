# instance-pool (+ scale)

A horizontally-scalable group of identical compute instances. Members are
created/destroyed automatically when you change the pool's `size`. Used as
the backing target for load-balancer services and for stateless
workloads.

## Model

```python
class InstancePool(ExoscaleModel):
    id: Optional[str]
    name: Optional[str]
    description: Optional[str]
    state: Optional[str]                  # "running" | "scaling-up" | "scaling-down" | ...
    size: Optional[int]                   # current desired size
    instance_type: Optional[Reference]
    template: Optional[Reference]
    disk_size: Optional[int]              # GiB
    instance_prefix: Optional[str]
    ipv6_enabled: Optional[bool]
    public_ip_assignment: Optional[str]
    labels: Optional[dict]
    deploy_target: Optional[Reference]
    ssh_key: Optional[Reference]
    created_at: Optional[str]
```

## CLI

```bash
exoscale-instance-pool list
exoscale-instance-pool get --id <uuid>
exoscale-instance-pool find --name <name>
exoscale-instance-pool create --json '{"name":"web-pool","size":1,"instance-type":{"id":"<type-id>"},"template":{"id":"<template-id>"},"disk-size":10,"ssh-key":{"name":"laptop"},"security-groups":[{"id":"<sg-id>"}]}'
exoscale-instance-pool delete --id <uuid>
```

## Library

```python
from exoscale_connector import ExoscaleClient
from exoscale_connector.resources.instance_pool import InstancePoolClient

pools = InstancePoolClient(ExoscaleClient.from_env(zone="de-fra-1"))

pool = pools.create({
    "name": "web-pool",
    "size": 1,
    "instance-type": {"id": "<type-id>"},
    "template": {"id": "<template-id>"},
    "disk-size": 10,
    "ssh-key": {"name": "laptop"},
    "security-groups": [{"id": "<sg-id>"}],
})

pools.scale(pool.id, 3)        # async — wait until state == "running" and size == 3
pools.update(pool.id, {"description": "production web"})
pools.delete(pool.id)          # cascade-deletes member instances
```

## Gotchas

- **`scale` is the colon-action endpoint `PUT instance-pool/{id}:scale`** with
  `{"size": <n>}`. Calls return as soon as the operation is accepted; the
  pool transitions through `scaling-up` / `scaling-down` and back to
  `running` over ~1 min per added/removed member.
- **Pool delete cascades to member instances** — they're terminated as part
  of the pool deletion. Wait for the operation to complete before reusing
  the names.
- **Pool members are visible via the `instance` API**, with `manager`
  populated. Don't delete them individually if you want the pool's desired
  size to stay correct.

## End-to-end example

Distilled from
[`tests/integration/test_tier_3.py::test_instance_pool_lifecycle`](../../tests/integration/test_tier_3.py):

```python
from exoscale_connector import ExoscaleClient
from exoscale_connector.resources.instance_pool import InstancePoolClient
from tests.integration._fixtures import (
    resolve_instance_type, resolve_linux_template, wait_for_state,
)

client = ExoscaleClient.from_env(zone="de-fra-1")
pools = InstancePoolClient(client)

pool = pools.create({
    "name": "demo-pool",
    "size": 1,
    "instance-type": {"id": resolve_instance_type(client, "standard.tiny")},
    "template": {"id": resolve_linux_template(client)},
    "disk-size": 10,
})

wait_for_state(lambda: pools.get(pool.id), "running", timeout=600)

pools.scale(pool.id, 2)
wait_for_state(lambda: pools.get(pool.id), "running", timeout=600)
assert pools.get(pool.id).size == 2

pools.scale(pool.id, 1)
wait_for_state(lambda: pools.get(pool.id), "running", timeout=600)

pools.delete(pool.id)
```
