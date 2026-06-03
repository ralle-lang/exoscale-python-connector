# Developer Guide

This guide explains how the connector is put together and how to extend it. If
you just want to *use* it, see the [user guide](user-guide.md).

## Design goals

1. **Self-contained and portable** — the package must work when copied into an
   unrelated repo. Runtime dependencies are limited to `requests` and `pydantic`.
   There are no imports from any host project and no environment-specific values
   baked in.
2. **Uniform per-asset clients** — every asset type behaves the same way
   (`list` / `get` / `find_by_name` / `create` / `update` / `delete`) so the API
   is predictable. Asset types only add code for what is genuinely special.
3. **Typed everywhere** — requests and responses are pydantic models.
4. **Secret-safe** — credentials are read from the environment only.

## Architecture

```
src/exoscale_connector/
  auth.py        ExoscaleV2Auth — EXO2-HMAC-SHA256 request signer (requests.AuthBase)
  config.py      ClientConfig — credentials, zone, endpoint, timeouts; from_env()
  errors.py      Typed exception hierarchy (ExoscaleError + subclasses)
  models.py      ExoscaleModel base (kebab-case aliasing), Operation, Reference
  client.py      ExoscaleClient — signed session, verb helpers, retries, operation polling
  resources/
    _base.py     ResourceClient[ModelT] — generic typed CRUD shared by all asset types
    <asset>.py   One module per asset type: its model(s) + its ResourceClient subclass
  cli/
    _base.py     run_resource_cli() — shared argparse harness
    <asset>.py   One thin CLI per asset type (wired to a console_script)
```

### Request flow

`ResourceClient.create()` → `ExoscaleClient.post()` → signed `requests` call →
the API returns either the resource directly or an **async operation** envelope
(`{id, state, reference}`). `ResourceClient` recognises the operation, polls it
via `ExoscaleClient.wait_operation()` until `state == "success"`, then re-fetches
the resource by `reference.id`. The poll loop tolerates a short run of transient
failures (connection drops, timeouts, a sporadic 404 while the operation is still
propagating) — up to `ClientConfig.max_poll_failures` (default 3) consecutive
failures are swallowed, the counter resetting on every successful poll. Errors
become typed exceptions (`NotFoundError` on 404, `APIError` otherwise,
`OperationError` on a failed op).

### Zones

The APIv2 is zone-scoped: the host is `https://api-<zone>.exoscale.com/v2`. A
single `ExoscaleClient` can target any zone — pass `zone=` per call, or set a
default on the client / config / `EXOSCALE_ZONE`. Globally-scoped resources (IAM,
DNS) are still served through a zone host.

### Field naming

The API uses kebab-case JSON keys (`flow-direction`, `start-port`). `ExoscaleModel`
maps them to snake_case Python attributes automatically via an alias generator, so
you write `rule.flow_direction` and the wire format stays correct. Unknown
server-side fields are preserved (`extra="allow"`), so the library keeps working
when the API adds fields ahead of us.

## Adding a new asset type

Each asset type is ~30–60 lines. Use `resources/security_group.py` as the
template. Steps:

1. **Create `src/exoscale_connector/resources/<asset>.py`:**

   ```python
   from typing import Optional
   from ..models import ExoscaleModel
   from ._base import ResourceClient

   class ElasticIP(ExoscaleModel):
       id: Optional[str] = None
       ip: Optional[str] = None
       description: Optional[str] = None
       # ... fields from the API reference, snake_case ...

   class ElasticIPClient(ResourceClient[ElasticIP]):
       collection_path = "elastic-ip"      # the APIv2 collection path
       model = ElasticIP
       list_key = "elastic-ips"            # JSON key holding the array (or omit to infer)
   ```

   Add resource-specific endpoints (like security-group rule management) as extra
   methods that call `self.client` and reuse `_should_wait()` / `wait_operation()`.

2. **Add a CLI** `src/exoscale_connector/cli/<asset>.py`:

   ```python
   from ..resources.elastic_ip import ElasticIPClient
   from ._base import run_resource_cli

   def main() -> int:
       return run_resource_cli(
           ElasticIPClient,
           prog="exoscale-elastic-ip",
           description="Manage Exoscale Elastic IPs via the APIv2.",
       )
   ```

   For a CLI with a child resource (like `dns` records or `sks` nodepools), pass
   `primary=PrimaryResource(...)` and `sub_resources=[SubResource(...)]`; the
   harness then emits `<verb>-<noun>` commands (`list-domains`, `create-record`,
   …) wired to the matching client methods. A CLI whose verbs don't fit the
   generic CRUD shape (like `dbaas`) builds its own parser/dispatch but reuses
   the shared helpers (`base_parser`, `load_payload`, `dump`, `execute_cli`).

3. **Register the console script** in `pyproject.toml` under `[project.scripts]`:

   ```toml
   exoscale-elastic-ip = "exoscale_connector.cli.elastic_ip:main"
   ```

4. **Write unit tests** `tests/unit/test_<asset>.py` mirroring
   `tests/unit/test_security_group.py` — list/get/find/create(operation)/delete,
   all with mocked HTTP via `responses`. No network.

### Finding the right paths and fields

The OpenAPI reference is the *starting* point but not the source of truth —
live-test runs surfaced **15 spec-vs-reality divergences** (wrong wrapper keys,
wrong HTTP methods, unit mismatches, terminal state names, short/long type
aliasing, list-only endpoints, …). To avoid re-discovering them the slow way:

1. **Consult** the OpenAPI reference as the starting point:
   <https://openapi-v2.exoscale.com/>.
2. **Verify against the live API**, not just the spec — where they disagree the
   live API wins. The gotchas recorded on each asset-type page and in the
   [live test results](live-test-results.md) capture the divergences found so far.
3. **Always** add a live lifecycle test (see [live test plan](live-test-plan.md))
   before considering a new asset type done — the mocked unit tests can't
   catch a wrong wire key (the mock can use the same wrong key as the code,
   so both agree and both are wrong).

## Object Storage (SOS) is special

Exoscale SOS is **S3-compatible**, not part of the APIv2, and uses S3 SigV4
auth — not the EXO2-HMAC signer. Its client (`resources/object_storage.py`) wraps
`boto3` against the SOS endpoint and is installed via the `[sos]` extra. It does
**not** use `ExoscaleClient`.

## Testing

```bash
pip install -e ".[dev]"
pytest                      # unit tests only (mocked, no network)
pytest -m integration       # opt-in live smoke tests (see below)
ruff check .                # lint
mypy src                    # type-check
```

- **Unit tests** (`tests/unit/`) are mandatory and CI-safe: every resource's
  request shaping, response parsing, and error handling is covered with mocked
  HTTP. They never hit the network.
- **Integration tests** (`tests/integration/`) are opt-in and tiered. Enable
  read-only smoke tests with `EXOSCALE_RUN_LIVE_TESTS=1` plus credentials and
  `EXOSCALE_TEST_ZONE`. Mutating tests need `EXOSCALE_ALLOW_MUTATION=1` plus
  the per-tier flag for what you want to exercise:

  | Tier | Flag | Cost / time |
  |---|---|---|
  | 1 — free non-compute | `EXOSCALE_TEST_TIER_1=1` | €0 |
  | 1 — api-key sub-tier | `EXOSCALE_TEST_TIER_1_API_KEY=1` | €0 |
  | 2 — cheap, no compute | `EXOSCALE_TEST_TIER_2=1` | < €0.01 |
  | 3 — compute | `EXOSCALE_TEST_TIER_3=1` | < €0.05, ~10–15 min |
  | 4 — LB / DBaaS / SKS | `EXOSCALE_TEST_TIER_4_LB`, `_DBAAS`, `_SKS` | each ~€0.01–0.05, 10–30 min |

  The connector ships **no** environment-specific defaults or allowlists —
  configure them for your own setup. See
  [live-test-plan.md](live-test-plan.md) for the per-asset design and
  [live-test-results.md](live-test-results.md) for the actual run log.

## Reference manual

The [asset type reference](asset-types/README.md) carries one page per asset
type — model, CLI, library, gotchas, end-to-end example. Every page is backed
by a passing live test. When you add a new asset type, add a matching page;
when you fix a bug surfaced by a live test, capture the lesson in the page's
"Gotchas" section.
