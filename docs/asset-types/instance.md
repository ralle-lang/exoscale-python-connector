# instance (+ lifecycle)

A compute virtual machine. The connector exposes full CRUD plus lifecycle
actions (start / stop / reboot) using the colon-action syntax on PUT.

## Model

```python
class SshKeyReference(ExoscaleModel):
    name: Optional[str]


class Instance(ExoscaleModel):
    id: Optional[str]
    name: Optional[str]
    state: Optional[str]              # "running" | "stopped" | "starting" | "stopping" | ...
    instance_type: Optional[Reference]
    template: Optional[Reference]
    disk_size: Optional[int]          # GiB
    public_ip: Optional[str]
    ipv6_address: Optional[str]
    ssh_key: Optional[SshKeyReference]
    labels: Optional[dict]
    manager: Optional[Reference]      # set when the instance is a pool member
    created_at: Optional[str]
```

## CLI

```bash
exoscale-instance list
exoscale-instance get --id <uuid>
exoscale-instance find --name <name>
exoscale-instance create --json '{"name":"web-01","instance-type":{"id":"<type-id>"},"template":{"id":"<template-id>"},"disk-size":10,"ssh-key":{"name":"laptop"},"security-groups":[{"id":"<sg-id>"}]}'
exoscale-instance delete --id <uuid>
```

> `start` / `stop` / `reboot` are exposed via the library client.

## Library

```python
from exoscale_connector import ExoscaleClient
from exoscale_connector.resources.instance import InstanceClient

instances = InstanceClient(ExoscaleClient.from_env(zone="de-fra-1"))

# Create
instance = instances.create({
    "name": "web-01",
    "instance-type": {"id": "<type-id>"},        # resolve via /instance-type
    "template": {"id": "<template-id>"},         # resolve via /template
    "disk-size": 10,                              # GiB
    "ssh-key": {"name": "laptop"},
    "security-groups": [{"id": "<sg-id>"}],
})

# Lifecycle
instances.stop(instance.id)
instances.start(instance.id)
instances.reboot(instance.id)

# Update + delete
instances.update(instance.id, {"labels": {"role": "web"}})
instances.delete(instance.id)
```

## Gotchas

- **Lifecycle actions are PUT, not POST.** The API returns 404 on POST;
  caught and fixed by the Tier 3 live test.
- **`instance-type` and `template` are References (`{"id": ...}`)**, not
  bare strings. Resolve their ids with
  `client.get("instance-type")` / `client.get("template")`. The Tier 3 test
  helpers `resolve_instance_type(name)` and `resolve_linux_template()` do
  this for you.
- **State transitions are asynchronous.** Create returns once the operation
  is accepted; the actual transition to `running` takes ~30-60 s. Same for
  stop/start/reboot. The Tier 3 test uses a `wait_for_state(getter,
  expected, timeout)` helper.
- **Type change requires a stop/start cycle** (no online vertical scaling).

## End-to-end example

Distilled from
[`tests/integration/test_tier_3.py::test_instance_lifecycle`](../../tests/integration/test_tier_3.py):

```python
from exoscale_connector import ExoscaleClient
from exoscale_connector.resources.instance import InstanceClient
from tests.integration._fixtures import (
    resolve_instance_type, resolve_linux_template, wait_for_state,
)

client = ExoscaleClient.from_env(zone="de-fra-1")
instances = InstanceClient(client)

inst = instances.create({
    "name": "demo-instance",
    "instance-type": {"id": resolve_instance_type(client, "standard.tiny")},
    "template": {"id": resolve_linux_template(client)},
    "disk-size": 10,
    "ssh-key": {"name": "<your-key-name>"},
    "security-groups": [{"id": "<sg-id>"}],
})

wait_for_state(lambda: instances.get(inst.id), "running", timeout=600)

instances.stop(inst.id)
wait_for_state(lambda: instances.get(inst.id), "stopped", timeout=300)

instances.start(inst.id)
wait_for_state(lambda: instances.get(inst.id), "running", timeout=300)

instances.delete(inst.id)
```
