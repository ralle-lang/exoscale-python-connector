# event (audit log)

The account **audit log**: one entry per APIv2 request, recording who called
(IAM user / role / API key), what they called (method + path), from where, and
the outcome. Handy as a "what changed / who did it" check after an automated
provisioning run. **Read-only.**

## Model

```python
class Event(ExoscaleModel):
    timestamp: Optional[str]        # ISO-8601 request time
    handler: Optional[str]          # the API handler that served the request
    uri: Optional[str]              # request path
    status: Optional[int]           # HTTP status code
    elapsed_ms: Optional[int]       # server-side duration
    request_id: Optional[str]
    source_ip: Optional[str]
    message: Optional[str]
    zone: Optional[str]
    iam_user: Optional[Reference]   # caller identity (whichever applies)
    iam_role: Optional[Reference]
    iam_api_key: Optional[Reference]
```

## CLI

```bash
exoscale-event list
```

## Library

```python
from exoscale_connector import ExoscaleClient
from exoscale_connector.resources.event import EventClient

events = EventClient(ExoscaleClient.from_env(zone="de-fra-1"))

# Recent window (API default)
for e in events.list():
    print(e.timestamp, e.status, e.uri, e.source_ip)

# Bounded window (ISO-8601). `from_` maps to the API's `from` query param.
recent = events.list(from_="2026-07-01T00:00:00Z", to="2026-07-08T00:00:00Z")
```

## Gotchas

- **Read-only, list-only.** There is a single endpoint (`GET /event`); no `get`
  by id, and events are not addressable by name.
- **Bare-array response.** Unlike most endpoints, `GET /event` returns a raw
  JSON array rather than a `{"events": [...]}` envelope. `EventClient.list`
  normalises that for you.
- **`from_`, not `from`.** The API's `from` query parameter collides with the
  Python keyword, so the client method takes `from_`.
- **Zone-scoped.** Events are read from the client's zone; query each zone you
  operate in if you need a full picture.
