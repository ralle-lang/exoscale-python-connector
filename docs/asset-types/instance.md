# instance (+ lifecycle)

A compute virtual machine. The connector exposes full CRUD plus lifecycle
actions (start / stop / reboot) using the colon-action syntax on PUT.

## Model

```python
class SshKeyReference(ExoscaleModel):
    name: Optional[str]


class InstancePrivateNetwork(ExoscaleModel):
    id: Optional[str]
    mac_address: Optional[str]


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
    # Attachments (read them here; change them via attach/detach endpoints)
    anti_affinity_groups: Optional[List[Reference]]
    elastic_ips: Optional[List[Reference]]
    private_networks: Optional[List[InstancePrivateNetwork]]
    ssh_keys: Optional[List[SshKeyReference]]   # every key; ssh_key is the shorthand
    user_data: Optional[str]                    # cloud-init, base64
    public_ip_assignment: Optional[str]         # "inet4" | "dual" | "none"
    mac_address: Optional[str]
    disk_encrypted: Optional[bool]
    secureboot_enabled: Optional[bool]
    tpm_enabled: Optional[bool]
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

# Boot a stopped instance into Rescue Mode ("netboot-efi" for UEFI templates)
instances.start(instance.id, rescue_profile="netboot")

# Protection, password, disk
instances.add_protection(instance.id)          # delete now fails until removed
instances.remove_protection(instance.id)
instances.reset_password(instance.id)          # instance stopped
password = instances.reveal_password(instance.id)   # a credential: never log it
instances.resize_disk(instance.id, 20)         # GiB, grow only, instance stopped
instances.enable_tpm(instance.id)
instances.revert_to_snapshot(instance.id, snapshot_id)   # instance stopped
instances.reset(instance.id)                   # re-install: WIPES the disk; stopped

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
- **Rescue Mode is a start option.** `start(id, rescue_profile=...)` sends
  `{"rescue-profile": ...}` on `PUT instance/{id}:start`. The spec allows
  `netboot` and `netboot-efi`; pick the one matching the template's
  `boot_mode` (`legacy` → `netboot`, `uefi` → `netboot-efi`). The instance must
  be stopped first.
- **Clear an optional field with `reset_field(id, "labels")`.** It wraps
  `DELETE /instance/{id}/{field}`; the spec allows `labels`. Use it
  instead of sending an empty value through `update`.
- **`reset()` wipes the disk.** It re-installs from the instance's template
  (or `template_id=`) and can change `disk_size=` at the same time. The
  instance must be stopped (`400 The instance needs to be stopped`). It is
  library-only, like the other destructive actions.
- **Stopping a Rescue Mode boot can take minutes.** A netbooted rescue system
  may ignore the graceful shutdown, so the stop only completes once Exoscale
  forces it.
- **Disks only grow.** `resize_disk(id, size)` rejects a smaller size;
  `revert_to_snapshot(id, snapshot_id)` needs the instance stopped and a
  snapshot of that same instance.
- **`reveal_password()` returns a credential.** It reads
  `GET instance/{id}:password`; treat the value like any secret and never log
  it. `reset_password()` generates a new one first and needs the instance
  stopped (`409 Instance must be stopped prior to the update` otherwise,
  observed live).

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

## Vertical scaling and reverse DNS

Vertical scaling is live-verified (Tier 3 `test_instance_scale`, 2026-06-10:
`standard.tiny` → `standard.small` on a stopped instance). Reverse DNS shares
its implementation with the elastic-ip variant, which is live-verified
(Tier 2); the instance-specific calls themselves have not been exercised
live — note the set call is a **POST** (the spec-suggested PUT 404s,
confirmed live on the elastic-ip endpoint).

```python
# Vertical scaling — instance must be STOPPED first.
instances.stop(inst.id)
instances.scale(inst.id, new_type_id)        # PUT /instance/{id}:scale

# Reverse DNS (PTR record).
instances.set_reverse_dns(inst.id, "host.example.com.")
instances.get_reverse_dns(inst.id)           # "host.example.com." | None
instances.delete_reverse_dns(inst.id)
```
