# deploy-target

A **deploy target** is a placement location an instance can be pinned to at
creation time — an `edge` site or a `dedicated` host. Targets are provisioned by
Exoscale, so this asset is **read-only**: discover a target id, then reference it
when creating an instance.

## Model

```python
class DeployTarget(ExoscaleModel):
    id: Optional[str]
    name: Optional[str]
    description: Optional[str]
    type: Optional[str]        # "edge" | "dedicated"
```

## CLI

```bash
exoscale-deploy-target list
exoscale-deploy-target get --id <uuid>
```

## Library

```python
from exoscale_connector import ExoscaleClient
from exoscale_connector.resources.deploy_target import DeployTargetClient
from exoscale_connector.resources.instance import InstanceClient

client = ExoscaleClient.from_env(zone="de-fra-1")

# 1. Discover an available target
targets = DeployTargetClient(client).list()
target = next(t for t in targets if t.type == "dedicated")

# 2. Pin a new instance to it
instance = InstanceClient(client).create({
    "name": "pinned-vm",
    "instance-type": {"id": "<instance-type-uuid>"},
    "template": {"id": "<template-uuid>"},
    "disk-size": 50,
    "deploy-target": {"id": target.id},
})

# The chosen target round-trips on the instance:
assert instance.deploy_target.id == target.id
```

## Gotchas

- **Read-only.** Only `list` / `get` are meaningful. Deploy targets are created
  by Exoscale; the inherited mutating verbs will fail server-side.
- **Set at create time only.** The `deploy-target` reference is a create-payload
  field on the instance (`{"deploy-target": {"id": ...}}`); it is not something
  you change on an existing instance. It round-trips as `Instance.deploy_target`.
- **Most accounts see an empty list.** Dedicated/edge placement is an opt-in
  capability; an empty `list()` just means none are assigned to your account.
