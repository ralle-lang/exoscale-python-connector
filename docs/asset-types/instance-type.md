# instance-type

Read-only catalogue of compute offerings (CPU/memory sizes). Humans know types
as `family.size` (`standard.tiny`); the API addresses them by UUID —
`InstanceTypeClient.find` translates.

## Model

| Field | Type | Notes |
|---|---|---|
| `id` | str (uuid) | |
| `family` | str | `standard`, `cpu`, `memory`, `gpu`, … |
| `size` | str | `tiny`, `small`, `medium`, … |
| `cpus` | int | |
| `memory` | int | **bytes** |
| `gpus` | int | |
| `authorized` | bool | whether your org may use the type |
| `slug` | property | derived `family.size` form |

## CLI

```bash
exoscale-instance-type list-instance-types
exoscale-connector instance-type --output table list-instance-types
```

## Library

```python
from exoscale_connector.resources.instance_type import InstanceTypeClient

types = InstanceTypeClient(client)
tiny = types.find("standard.tiny")     # InstanceType | None
inst = instances.create({"instance-type": {"id": tiny.id}, ...})
```

## Gotchas

- **`authorized=False`** types appear in the list but cannot be used —
  filter on it before offering choices to users.
- **Live verification:** smoke test (`test_list_instance_types_and_find_slug`)
  ran 2026-06-10 against `at-vie-1`; the wire shape also matches what the
  Tier 3 fixtures (`resolve_instance_type`) have always exercised live.
