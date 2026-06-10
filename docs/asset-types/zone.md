# zone

Read-only catalogue of Exoscale zones (`GET /zone`). Use it instead of
hardcoding zone names — `config.KNOWN_ZONES` is only a static hint list, this
is the live answer. Note the chicken-and-egg: the APIv2 host is itself
zone-scoped, so one working zone (or an endpoint override) is needed to list
the others.

## Model

| Field | Type | Notes |
|---|---|---|
| `name` | str | e.g. `de-fra-1` |
| `api_endpoint` | str | the zone's API host, when advertised |

## CLI

```bash
exoscale-zone list-zones
exoscale-connector zone --output table list-zones
```

## Library

```python
from exoscale_connector.resources.zone import ZoneClient

zones = ZoneClient(client).list()
names = [z.name for z in zones]
```

## Gotchas

- **Read-only.** The inherited mutating verbs exist on the class but are not
  supported by the API.
- **Live verification:** covered by a smoke test (`test_list_zones`); pending
  its first recorded run.
