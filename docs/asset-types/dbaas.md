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
    # A LIST of URIs for Postgres (primary + replicas) and the other data
    # engines; a single string for Grafana.
    uri: Optional[Union[str, List[str]]]


class DBaaSService(ExoscaleModel):
    name: Optional[str]            # the unique identifier (used in URL paths)
    type: Optional[str]            # short form: "pg", "mysql", "valkey", ...
    plan: Optional[str]            # e.g. "hobbyist-2", "startup-4"
    state: Optional[str]           # "rebuilding" -> "running"
    version: Optional[str]         # engine version; settable on update (mysql/valkey/clickhouse/...)
    node_count: Optional[int]
    disk_size: Optional[int]
    ip_filter: Optional[List[str]]  # allowed CIDRs; absent/empty = allow-all
    created_at: Optional[str]
    uri_params: Optional[DBaaSConnectionInfo]
    uri: Optional[str]
    connection_info: Optional[DBaaSConnectionInfo]
    databases: Optional[List[str]]  # pg/mysql: databases inside the service
    connection_pools: Optional[List[DBaaSConnectionPool]]  # pg: name, database, username, mode, size, connection_uri (hidden from repr)


class DBaaSLogEntry(ExoscaleModel):
    time: Optional[str]
    node: Optional[str]
    unit: Optional[str]
    message: Optional[str]


class DBaaSServiceLogs(ExoscaleModel):     # get_logs() page
    logs: Optional[List[DBaaSLogEntry]]
    offset: Optional[str]                  # cursor for the next page
    first_log_offset: Optional[str]


class DBaaSTask(ExoscaleModel):            # get_task() / check_upgrade()
    id: Optional[str]
    task_type: Optional[str]
    success: Optional[bool]
    result: Optional[str]
    result_codes: Optional[List[DBaaSTaskResultCode]]   # code + dbname
    create_time: Optional[str]


class DBaaSMigrationStatus(ExoscaleModel): # get_migration_status()
    status: Optional[str]
    method: Optional[str]
    error: Optional[str]
    details: Optional[List[DBaaSMigrationDetail]]       # per database: dbname, method, status, error


class DBaaSValkeyUser(ExoscaleModel):      # list_valkey_users() item
    username: Optional[str]
    type: Optional[str]
    access_control: Optional[DBaaSValkeyAccessControl]  # categories, commands, keys, channels
```

## CLI

The DBaaS CLI keeps bespoke verbs (built on the shared CLI plumbing) because
`create` needs `--type` and `--name` separately from the JSON body, and services
are addressed by name rather than id:

```bash
exoscale-dbaas list
exoscale-dbaas get --name <name>
exoscale-dbaas create --type pg --name my-pg-1 --json '{"plan": "hobbyist-2"}'
# Payloads with secrets (e.g. admin-password): read them from stdin or a file
# so they never appear in the process list.
printf '%s' "$PG_CREATE_BODY" | exoscale-dbaas create --type pg --name my-pg-1 --file -
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
- **`connection-info.uri` is usually a LIST**, not a string. Postgres
  returns multiple endpoint URIs (primary + replicas), as do the other data
  engines — but **Grafana returns a single string**. The model accepts both,
  so check `isinstance(uri, str)` before iterating.
- **There are TWO `uri` fields with different shapes.** `DBaaSService.uri`
  is a scalar `Optional[str]` — the canonical hostname-based URI for the
  service. `DBaaSConnectionInfo.uri` (nested inside `connection_info`) is
  `Optional[Union[str, List[str]]]` — the per-endpoint URIs, typically
  IP-based, one per node (a single string for Grafana). Both are populated by the live API; they are not duplicates.
- **Provisioning takes 5–15 minutes** on the cheapest plans; longer on
  larger plans. Use a generous timeout in `wait_for_state`.
- **Mutations return an operation, awaited by default.** Per the spec,
  create/update, `create_user`/`delete_user`/`reset_user_password`,
  `create_database`/`delete_database`, `start_maintenance` and `delete` all
  answer with an operation. The
  connector awaits it unless `wait=False`; the user/maintenance methods
  return the settled envelope as a dict. A settled operation does **not**
  mean the service is `running` (it passes through `rebuilding`), so
  `wait_for_state` remains the follow-up after create.
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
assert conn.connection_info.uri  # list of URIs (a single string for Grafana)

# Reveal admin password (single-shot endpoint)
pw = dbaas.reveal_user_password(name, "avnadmin", service_type="pg")
assert pw["password"]

dbaas.delete(name)
```

## Service updates and user management

`update()`, `create_user()` and `delete_user()` are live-verified (extended
Tier 4 pg lifecycle, 2026-06-10). `reset_user_password()` is implemented from
the API reference only — the live test doesn't call
it (resetting `avnadmin`'s password mid-test would be disruptive for no
extra wire-shape coverage):

```python
# Plan change / maintenance window / type-specific settings.
dbaas.update(name, {"maintenance": {"dow": "sunday", "time": "04:00:00"}}, service_type="pg")

# Engine version upgrade (mysql / valkey / clickhouse / ...): `version` is a
# first-class update field, round-tripped on the model.
dbaas.update("my-mysql-1", {"version": "8"}, service_type="mysql")

# Users — passwords are never returned by create/reset; fetch them
# explicitly (and treat them as secrets).
dbaas.create_user(name, "analyst", service_type="pg")
dbaas.reset_user_password(name, "analyst", service_type="pg")
secret = dbaas.reveal_user_password(name, "analyst", service_type="pg")
dbaas.delete_user(name, "analyst", service_type="pg")

# Engine-specific user options (ValueError on the wrong engine):
dbaas.create_user(name, "replicator", service_type="pg", allow_replication=True)
dbaas.create_user("my-mysql-1", "app", service_type="mysql",
                  authentication="caching_sha2_password")
dbaas.create_user("my-valkey-1", "app", service_type="valkey",
                  access_control={"categories": ["+@read"], "keys": ["app:*"]})
# Set a chosen password (from a secret store, never a literal); omit it to
# let the API generate one. mysql can switch the auth plugin at the same time.
dbaas.reset_user_password(name, "analyst", service_type="pg", password=new_password)
```

The engine-specific user options and the `password` argument are implemented
from the API reference — pending live verification.

### Databases (pg / mysql)

A new service only holds its default database. Create and drop further ones
inside it; the current list is the `databases` field of the type-specific
detail. Implemented from the API reference — pending live verification.

```python
dbaas.create_database(name, "app", service_type="pg", lc_collate="C", lc_ctype="C")
dbaas.get_connection_info(name, service_type="pg").databases  # ["defaultdb", "app"]
dbaas.delete_database(name, "app", service_type="pg")
```

- Only pg and mysql have a database sub-resource; any other `service_type`
  raises `ValueError` before a request is sent.
- `lc_collate` / `lc_ctype` are PostgreSQL locale settings; passing them for
  mysql raises `ValueError`.
- Both methods await their operation unless `wait=False`.

### TLS trust, logs and metrics

Engine-generic reads. `get_ca_certificate` is live-verified (2026-10-08);
`get_logs` / `get_metrics` are implemented from the API reference — pending
live verification (no DBaaS service on the test tenant):

```python
# The CA that signs every DBaaS server certificate. Pin it to verify the host
# from get_connection_info(), e.g. libpq sslmode=verify-full sslrootcert=<file>.
pem = dbaas.get_ca_certificate()

# Logs page through an opaque cursor: pass the previous page's offset back.
page = dbaas.get_logs(name, limit=100, sort_order="desc")
for entry in page.logs or []:
    print(entry.time, entry.node, entry.message)
older = dbaas.get_logs(name, offset=page.offset)

# Metrics for a period (hour / day / week / month / year); engine-specific
# series, so a raw dict.
metrics = dbaas.get_metrics(name, period="day")
```

- `get_logs` and `get_metrics` are reads even though the API exposes them as
  `POST` (the options travel in the body); they never change the service.
- Log lines can contain query text or client addresses — treat them like any
  other operational data and keep them out of shared CI output.

### Generic engine sub-resources (settings / ACL / maintenance)

Three read/trigger helpers that generalise across engine types.
`get_settings` is live-verified (Tier 4 pg lifecycle); `get_acl_config` /
`start_maintenance` are implemented from the API reference — pending live
verification:

```python
# Discover the settings schema an engine accepts (short type form: "pg", not
# "postgres"). Response shape is engine-specific -> raw dict.
schema = dbaas.get_settings("pg")                   # GET /dbaas-settings-pg

# Per-service ACL configuration (kafka / opensearch).
acls = dbaas.get_acl_config("my-kafka-1", service_type="kafka")

# Run the pending maintenance update now instead of waiting for the window.
dbaas.start_maintenance("my-pg-1", service_type="pg")
```

- **`get_settings` uses the short type form** (`pg`, `mysql`, `clickhouse`) — the
  same names `list_service_types()` returns — because the endpoint is
  `/dbaas-settings-{short}`. The per-service `get_acl_config` /
  `start_maintenance` use the long type path (`pg` → `postgres`) like the rest of
  the type-specific methods; pass either form and the client translates.

- **ClickHouse is out of scope** (roadmap D4). It is not enabled on a default
  Exoscale tenant — every ClickHouse operation returns `403 "... not enabled"`,
  read-only ones included — so nothing about it can be live-verified here.
  `service_type="clickhouse"` is still accepted by the engine-generic methods;
  it is simply unsupported. The `get_settings` / `start_maintenance` helpers
  above work for every engine; `get_acl_config` applies to kafka and
  opensearch.
- **`delete_user` is unverified for ClickHouse.** Upstream moved that engine's
  delete to `DELETE /dbaas-clickhouse/{name}/user/{user-uuid}` — path parameter
  renamed *and* retyped to a UUID, which is consistent with ClickHouse carrying
  a per-user `uuid` upstream. Every other engine still deletes by username, as
  do ClickHouse's own `password/reset` and `password/reveal`. The connector
  still sends whatever you pass, so `delete_user(..., service_type="clickhouse")`
  may not resolve a username, and the connector exposes no user-listing method
  to read a uuid from today. Live verification was attempted 2026-08-01 and is
  blocked — ClickHouse is a per-account product and is not enabled on the test
  tenant, so every ClickHouse operation returns `403 "... not enabled"`,
  read-only ones included.

### Engine-specific operations

Operations that exist for one engine (or a few) only. All are implemented from
the API reference — pending live verification:

```python
# Migration from an external pg / mysql / valkey database. The source URI
# carries admin credentials: read it from a secret store, never a literal.
op = dbaas.check_migration(name, source_uri, method="dump")
task = dbaas.get_task(name, op["reference"]["id"])        # DBaaSTask
status = dbaas.get_migration_status(name)                 # DBaaSMigrationStatus
dbaas.stop_migration(name, service_type="pg")             # pg / mysql / valkey

# PostgreSQL: PgBouncer connection pools, replication privilege, upgrade check
dbaas.create_connection_pool(name, "app-pool", "app", mode="transaction", size=20)
dbaas.get_connection_info(name, service_type="pg").connection_pools  # current pools
dbaas.update_connection_pool(name, "app-pool", size=40)
dbaas.delete_connection_pool(name, "app-pool")
users = dbaas.set_allow_replication(name, "replicator", True)   # the service's users
check = dbaas.check_upgrade(name, "17")                   # DBaaSTask; changes nothing

# MySQL: lift the read-only mode a full disk triggers, briefly
dbaas.enable_writes("my-mysql-1")

# Kafka: topic and Schema Registry ACL entries (ids via get_acl_config)
dbaas.add_kafka_topic_acl("my-kafka-1", "app", "orders-*", "readwrite")
dbaas.delete_kafka_topic_acl("my-kafka-1", acl_id)
dbaas.add_kafka_schema_registry_acl("my-kafka-1", "app", "Subject:orders-*",
                                    "schema_registry_read")
dbaas.delete_kafka_schema_registry_acl("my-kafka-1", acl_id)
connect = dbaas.reveal_kafka_connect_password("my-kafka-1")  # a secret: never print

# OpenSearch: replace the ACL config
dbaas.set_opensearch_acl_config("my-os-1", acl_enabled=True, acls=[
    {"username": "app", "rules": [{"index": "logs-*", "permission": "read"}]},
])

# Valkey: users with their ACLs
for user in dbaas.list_valkey_users("my-valkey-1"):
    print(user.username, user.access_control)
dbaas.update_valkey_user_access_control("my-valkey-1", "app", {"keys": ["app:*"]})
```

- **`check_migration` and `check_upgrade` only check.** Neither starts a
  migration or an upgrade; the result lands in a `DBaaSTask`. A migration
  itself starts by creating or updating the service with a `migration` block.
- **`set_allow_replication` and `check_upgrade` answer directly**, not with an
  operation, so they take no `wait` argument.
- **[BETA] DBaaS operations are not wrapped**: integrations between services,
  external endpoints (Datadog, Prometheus, rsyslog, Elasticsearch, OpenSearch)
  and everything ClickHouse. The connector ships no `[BETA]` operation without
  the maintainer's explicit OK; `scripts/request_field_audit.py` lists them
  separately.

`ensure()` is **not** supported for DBaaS (create needs `service_type`/`name`
kwargs) — use `get_or_none(name)` + `create(...)` explicitly.
