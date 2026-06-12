# dbaas (managed databases)

Exoscale's Aiven-backed managed database service. Supports Postgres (`pg`),
MySQL (`mysql`), Valkey/Redis (`valkey`), OpenSearch (`opensearch`), Kafka
(`kafka`), Grafana (`grafana`), Thanos (`thanos`). **Services are
identified by name, not UUID.**

## Model

```python
class DBaaSConnectionInfo(ExoscaleModel):
    host: Optional[str]
    port: Optional[int]
    user: Optional[str]
    dbname: Optional[str]
    ca: Optional[str]              # PEM-encoded TLS CA cert (single string)
    # The wire field is a LIST of URIs for Postgres (primary + replicas).
    # Other service types may differ — this is the most general shape.
    uri: Optional[List[str]]


class DBaaSService(ExoscaleModel):
    name: Optional[str]            # the unique identifier (used in URL paths)
    type: Optional[str]            # short form: "pg", "mysql", "valkey", ...
    plan: Optional[str]            # e.g. "hobbyist-2", "startup-4"
    state: Optional[str]           # "rebuilding" -> "running"
    node_count: Optional[int]
    disk_size: Optional[int]
    ip_filter: Optional[List[str]]  # allowed CIDRs; absent/empty = allow-all
    created_at: Optional[str]
    uri_params: Optional[DBaaSConnectionInfo]
    uri: Optional[str]
    connection_info: Optional[DBaaSConnectionInfo]
```

## CLI

The DBaaS CLI keeps bespoke verbs (built on the shared CLI plumbing) because
`create` needs `--type` and `--name` separately from the JSON body, and services
are addressed by name rather than id:

```bash
exoscale-dbaas list
exoscale-dbaas get --name <name>
exoscale-dbaas create --type pg --name my-pg-1 --json '{"plan": "hobbyist-2"}'
exoscale-dbaas delete --name <name>
```

## Library

```python
from exoscale_connector import ExoscaleClient
from exoscale_connector.resources.dbaas import DBaaSServiceClient

dbaas = DBaaSServiceClient(ExoscaleClient.from_env(zone="de-fra-1"))

# Discover the cheapest plan and create a service
plan = "hobbyist-2"
dbaas.create({"plan": plan}, service_type="pg", name="my-pg-1")

# Lock the service down to an IP allow-list (CIDRs). DBaaS can't join a
# private network, so ip-filter + TLS is the primary way to secure it.
dbaas.create(
    {"plan": plan, "ip-filter": ["203.0.113.0/24"]},
    service_type="pg",
    name="app-pg",
)
# Tighten or widen it later via update (replaces the whole list):
dbaas.update("app-pg", {"ip-filter": ["203.0.113.0/24", "198.51.100.7/32"]}, service_type="pg")

# Fetch (two-step lookup: list -> discover type -> type-specific GET)
svc = dbaas.get("my-pg-1")
print(svc.state)

# Connection info (host/port/user/uri); never log/print the values.
conn = dbaas.get_connection_info("my-pg-1", service_type="pg")
host = conn.uri_params.host

# Reveal user password — single-shot reveal endpoint
pw_response = dbaas.reveal_user_password("my-pg-1", "avnadmin", service_type="pg")
password = pw_response["password"]

dbaas.delete("my-pg-1")

# Helpers
plans = dbaas.list_service_types()
```

## Gotchas

- **Short/long type names mismatch.** The API lists service types with
  *short* names (`pg`, `valkey`) but URL paths use *long* names
  (`postgres`). The connector keeps an alias map; callers may pass either.
  The only real mismatch in current use is `pg → postgres`.
- **`GET /dbaas-service/<name>` is list-only.** The generic collection
  path returns 404 on individual item GETs. The connector overrides
  `get()` to do a two-step lookup: list to discover the type, then fetch
  the detail body via the type-specific `dbaas-<long-type>/<name>` path.
- **`DELETE /dbaas-service/<name>` IS valid** (delete uses the generic
  path even though GET doesn't). Same path, different methods. ¯\\_(ツ)_/¯
- **`connection-info.uri` is a LIST**, not a string. Postgres returns
  multiple endpoint URIs (primary + replicas). The model field reflects
  this.
- **There are TWO `uri` fields with different shapes.** `DBaaSService.uri`
  is a scalar `Optional[str]` — the canonical hostname-based URI for the
  service. `DBaaSConnectionInfo.uri` (nested inside `connection_info`) is
  `Optional[List[str]]` — the per-endpoint URIs, typically IP-based, one
  per node. Both are populated by the live API; they are not duplicates.
- **Provisioning takes 5–15 minutes** on the cheapest plans; longer on
  larger plans. Use a generous timeout in `wait_for_state`.
- **The create response carries no `reference`** — the connector
  re-fetches from the type-specific path it just hit. Live test registers
  cleanup BEFORE create to avoid orphan leakage if the re-fetch fails.
- **`reveal_user_password` returns a raw `dict`, not a typed model.** The
  response shape is type-specific (Postgres has `password`, MySQL/Valkey
  may carry additional fields like ports). Keeping it as a dict avoids
  forcing a tight schema that varies per backend.
- **`ip-filter` is a typed field (`DBaaSService.ip_filter`) and your main
  security lever.** It's a list of CIDR strings, e.g. `["203.0.113.0/24"]`,
  settable through the create/update payload (wire key `ip-filter`) and read
  back as `svc.ip_filter`. **A managed DB can't join a private network**, so an
  `ip-filter` allow-list plus TLS (the CA cert lives in `connection_info.ca`)
  is the primary way to keep the service from being reachable by the whole
  internet. `update` **replaces** the entire list rather than merging, so pass
  the full set each time. An empty/absent filter means *allow all*.

## End-to-end example

Distilled from
[`tests/integration/test_tier_4.py::test_dbaas_pg_lifecycle`](../../tests/integration/test_tier_4.py):

```python
from exoscale_connector import ExoscaleClient
from exoscale_connector.resources.dbaas import DBaaSServiceClient
from tests.integration._fixtures import resolve_cheapest_dbaas_plan, wait_for_state

client = ExoscaleClient.from_env(zone="de-fra-1")
dbaas = DBaaSServiceClient(client)

plan = resolve_cheapest_dbaas_plan(client, "pg")
name = "demo-pg-1"

dbaas.create({"plan": plan}, service_type="pg", name=name)
wait_for_state(lambda: dbaas.get(name), "running", timeout=1800, interval=15)

# Connection info (don't print the values)
conn = dbaas.get_connection_info(name, service_type="pg")
assert conn.uri_params.host and conn.uri_params.port
assert conn.connection_info.uri  # list of URIs

# Reveal admin password (single-shot endpoint)
pw = dbaas.reveal_user_password(name, "avnadmin", service_type="pg")
assert pw["password"]

dbaas.delete(name)
```

## Service updates and user management

`update()`, `create_user()` and `delete_user()` are live-verified (extended
Tier 4 pg lifecycle, 2026-06-10). `reset_user_password()` is the one method
still implemented from the API reference only — the live test doesn't call
it (resetting `avnadmin`'s password mid-test would be disruptive for no
extra wire-shape coverage):

```python
# Plan change / maintenance window / type-specific settings.
dbaas.update(name, {"maintenance": {"dow": "sunday", "time": "04:00:00"}}, service_type="pg")

# Users — passwords are never returned by create/reset; fetch them
# explicitly (and treat them as secrets).
dbaas.create_user(name, "analyst", service_type="pg")
dbaas.reset_user_password(name, "analyst", service_type="pg")
secret = dbaas.reveal_user_password(name, "analyst", service_type="pg")
dbaas.delete_user(name, "analyst", service_type="pg")
```

`ensure()` is **not** supported for DBaaS (create needs `service_type`/`name`
kwargs) — use `get_or_none(name)` + `create(...)` explicitly.
