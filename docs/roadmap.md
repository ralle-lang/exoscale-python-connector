# Roadmap

Forward-looking plans and the reasoning behind them. Work items are written
issue-ready (one heading = one GitHub issue); the **Decisions** section records
the "why" so it survives even after issues are closed.

How we track: this file holds direction and rationale; GitHub issues/milestones
hold execution state. When an item graduates to an issue, link it here.

---

## Milestone: v0.2.0 — verified extensions ✅ shipped 2026-06-10/11

Everything on `fix/assessment-findings` and `feat/connector-extensions`,
validated against a live tenant and released.

### ✅ Run live verification for the fix + extensions branches
Tier 0–4 suite run 2026-06-10 with `EXOSCALE_RECORD=1`. Three spec-vs-reality
divergences found and fixed: `assume-role-policy` routes through generic PUT
body (not a `:`-subendpoint), reverse DNS uses POST not PUT, `get_lifecycle`
returns `None` not `[]` for unconfigured SOS buckets. All pending-live-verification
labels cleared from code and docs.

### ✅ Seed the recorded-fixture archive
12 JSONL files committed in `eb78136`. Email + API key id scrubbing added to
the recorder. CI replay active via `test_recorded_replay.py`.

### ✅ Merge to main, bump version, tag v0.2.0
Both branches merged to `main`. `pyproject.toml` + `__version__` bumped to
`0.2.0`, tagged, and published via the trusted-publishing workflow (issue #4).

### ✅ Configure PyPI trusted publishing (issue #4)
Done: the repo + `release.yml` are registered as a trusted publisher for
`exoscale-connector` on pypi.org, with the `pypi` GitHub environment. Releases
from `v0.2.0` onward publish over OIDC with no stored token. See the
[Releasing section](developer-guide.md#releasing) for the current flow.

---

## Milestone: Advisor — AI-assisted *learning*, not operation

An aid for people who don't know Exoscale or this connector yet: natural
language in, **explained code out, human executes**. See Decisions below for
why there is deliberately no AI execution layer. Rungs are ordered by
value-per-effort; each stands alone.

### ✅ Rung 1 — generated AI-ready reference bundle (`docs/llms.txt`) (issue #5)
Shipped 2026-06-11: `scripts/generate_llms_txt.py` introspects the package
(every `ResourceClient` subclass, method signatures, pydantic field tables)
and embeds all asset-type pages; sync enforced in CI by
`test_llms_txt.py::test_bundle_is_in_sync_with_code` plus an explicit
`--check` step.

A docs build step that generates one self-contained context file from ground
truth: the introspected API surface (every `ResourceClient` subclass, method
signatures, pydantic model fields — generated from code so it cannot drift)
plus the distilled asset-type pages with their live-verified gotchas. A
newcomer pastes it into whatever LLM they already use and gets accurate,
hallucination-free guidance citing real methods. No runtime AI, no new
dependencies; CI check that the bundle is in sync with the code. Lives in
this repo.

### ✅ Rung 2 — editor/assistant skill packaging (issue #6)
Shipped 2026-06-11: the generator now also emits the bundle as an agent skill
(`SKILL.md` + `reference.md`) in two places — inside the wheel
(`src/exoscale_connector/_skill/`, installed into any project via
`exoscale-connector skill install [--user|--dest]`) and repo-local
(`.claude/skills/exoscale-connector/`) for dogfooding. Same CI sync
enforcement as rung 1.

Package the rung-1 bundle as a skill for AI-assisted editors, so "how do I
give this instance more memory?" gets answered ambiently from verified docs
during normal work. Thin wrapper around rung 1.

### Rung 3 — read-only advisor MCP server (separate repo)
An MCP server exposing docs search plus *list-only* live catalogue queries
(zones, instance types, templates) — so the advisor can answer "what exists
in de-fra-1 right now" with live data while being structurally incapable of
mutation. **Separate repository** because it adds an MCP framework dependency
and a different risk/release profile, and the connector's "requests + pydantic
only" promise must hold. No mutation tools, by design, ever — see Decisions.

**Design + repo bootstrap shipped (issue #7, 2026-06-11):** the work lives in
[`ralle-lang/exoscale-mcp-advisor`](https://github.com/ralle-lang/exoscale-mcp-advisor).
The full design is its founding document,
[`docs/mcp-advisor-design.md`](https://github.com/ralle-lang/exoscale-mcp-advisor/blob/main/docs/mcp-advisor-design.md)
— tool surface (`search_docs`, `get_asset_page`, `list_zones`,
`list_instance_types`, `list_templates`), knowledge sourced zero-duplication
from this package's bundled `_skill/reference.md`, read-only enforced by a
structural test, and a four-layer test strategy. Implementation is tracked by
issues in that repo. Anything MCP-related lives there, not here.

---

## ✅ Upstream drift watch (CI) (issue #10, Advisor milestone)

Shipped 2026-06-11: `.github/workflows/upstream-drift.yml` (weekly cron),
seeded snapshots under `.github/upstream/`, agent-ready mapping via
`scripts/upstream_drift_map.py`, Dependabot keeping the action pins current.
One deviation from the original design: the official SDK is watched via its
**PyPI version** (`exoscale` package) rather than GitHub releases — the repo
publishes no releases, and PyPI is what users install anyway.

Mapped to the Advisor milestone: the bundle/skill promise verified knowledge
that cannot drift — CI enforces code↔docs sync, and this watch closes the
remaining gap (code+docs drifting from the live API). A weekly GitHub Actions
workflow that detects upstream changes and files an `upstream-drift` issue to
*evaluate* — never to auto-fix (consistent with D1: a spec diff is a prompt
for human+agent review, and with the repo's stance that the spec is the
starting point, not the truth).

**Watch targets** (different granularity each):
- **APIv2 OpenAPI spec** (`https://openapi-v2.exoscale.com/source.json`) —
  the real drift source for models, paths, and wrapper keys. Diffed in detail.
- **`python-exoscale` releases** — release-level only; a new release is the
  cue to re-check that the README's "relationship to the official SDK"
  paragraph still holds.

**Mechanism:**
- Commit a normalized snapshot (`jq -S`) of the spec under
  `.github/upstream/`, plus the last-seen SDK release tag.
- Weekly cron: fetch → normalize → diff with `oasdiff` (spec-aware,
  markdown changelog, ignores cosmetic churn). On change: file the issue
  via `--body-file` (injection hygiene — upstream text never interpolated
  into shell). The bot does **not** push the refreshed snapshot — main is
  protection-ruled and, per D1, the baseline should move only after a human
  triages the drift. The snapshot under `.github/upstream/` is advanced
  inside the reviewed triage PR instead (see the `exoscale-drift-triage`
  skill); re-runs before triage append a dedup comment.
- Dedup: append a comment to an existing open `upstream-drift` issue
  instead of opening duplicates.
- Issue body is agent-ready: oasdiff changelog + a changed-path →
  module/doc-page mapping (derivable from `collection_path` introspection,
  same machinery as `generate_llms_txt.py`) + a standing evaluation
  checklist (models, gotcha pages, live re-verification scope, regenerate
  AI artifacts).

**Dependency handling:** `oasdiff` is CI-only tooling (a pinned third-party
action, SHA-pinned) — it never touches `pyproject.toml`, so the
"requests + pydantic only" package promise holds. Add a minimal
`.github/dependabot.yml` (`github-actions` ecosystem, weekly) to keep the
pinned actions current — this also closes the pre-existing gap that
`checkout`/`setup-python` pins were never auto-updated. Renovate is not
needed (Dependabot is GitHub-native; no extra infrastructure).

---

## Backlog: APIv2 additive coverage (drift-fed)

Additive upstream changes (new optional request params worth promoting to
first-class, new endpoints, new asset types) accrue here as they surface in
`upstream-drift` issues. These are **not** per-item GitHub issues — they wait
until the pile is worth a focused session (see D3 for the triage rule and the
effort-based graduation trigger). Each item carries a first-pass effort
estimate including a full test run; when the running total crosses ~8–16h
(1–2 days), the batch graduates to one GitHub issue on the active milestone and
gets implemented together.

| Item | Source | First-pass estimate (impl + full test run) |
|---|---|---|
| **VPC asset type** — new `/vpc` client with nested `subnet` and `route` sub-resources (nested-resource shape like `sks.py` nodepools); model, CLI entry point, doc page, live verification. Subnet ops now include `PUT /vpc/{}/subnet/{}/attach` + `.../detach` (instance↔subnet membership); `POST .../route` dropped its `name` request property | drift #34, re-confirmed #40, subnet attach/detach + route-`name` drop #43 | ~1 day (new asset type, nested sub-resources, live verify) |
| **DBaaS MySQL + Valkey `version`** — expose the new optional request property on `PUT /dbaas-valkey/{name}` and `PUT /dbaas-mysql/{name}` (update) as a first-class param | drift #34 (Valkey), #40 (MySQL) | ~2h |
| **SKS nodepool `nvidia-mig-profiles`** — expose the new optional request property on nodepool create + update; add the response field to the model | drift #34, re-confirmed #40 | ~1–2h |
| **ClickHouse DBaaS engine** — the new `/dbaas-clickhouse/*` endpoints. Basic lifecycle (create/get/update/delete) and user + password management already work through the engine-generic `DBaaSServiceClient` via `service_type="clickhouse"` (no `_url_type` alias needed). Genuinely unmodelled sub-resources, none engine-specific: `GET /dbaas-settings-clickhouse` (settings discovery), `GET /dbaas-clickhouse/{}/acl-config`, `PUT /dbaas-clickhouse/{}/maintenance/start` — the settings/maintenance-start/acl patterns exist for other engines too and are unmodelled across the board, so promote them as generic DBaaS methods rather than ClickHouse-only. Affects `src/exoscale_connector/resources/dbaas.py`, `docs/asset-types/dbaas.md` | drift #43 | ~1–2h |
| **KMS asset type** — new `/kms-key` client (15 endpoints). Full lifecycle: CRUD, enable/disable, key rotation (`enable-`/`disable-key-rotation`, `rotate`, `list-key-rotations`), crypto ops (`encrypt`, `decrypt`, `re-encrypt`, `generate-data-key`), deletion lifecycle (`schedule-`/`cancel-deletion`), `replicate`. Model + CLI entry point + doc page + live verify. Build to the current spec shape — `POST /kms-key/{id}/schedule-deletion` dropped the required `status` response property in #43. Not in any current module | requested; touched by drift #43 | ~0.5–1 day (crypto ops + live verify) |
| **Deploy targets** — read-only `/deploy-target` (list) + `/deploy-target/{id}` (get); `type` is `edge`/`dedicated` (placement targets for instance deploys). Small read client; also wire the already-unmodelled `deploy-target` reference into `InstanceClient.create` so an instance can be pinned to a target. Affects `src/exoscale_connector/resources/instance.py` + new module | requested | ~2–3h |
| **Events / audit log** — read-only `/event` client (`GET /event`) returning the audit event stream, so an automated run can be followed by a "what changed / who did it" check. Model + read method + doc page | requested | ~2h |
| **Full security-group rule reference typing (private + public)** — today `SecurityGroupRule.security_group` is a bare `Reference` (id-only), which covers private peers but cannot express an Exoscale-managed **public** SG source/dest (needs `visibility: "public"`). Replace it with a dedicated `security-group-resource` model (`id`, `name`, `visibility`) so both private (`{id}`) and public (`{id, visibility}`) references are typed on request and round-tripped on response. Add a live test for a peer-SG-by-id rule — tier-1 currently only exercises a CIDR `network` rule. Affects `src/exoscale_connector/resources/security_group.py`, `models.py`, `docs/asset-types/security-group.md` | requested | ~2–3h |
| **VPC subnet `instances` attachment list** — `GET`/`PUT /vpc/{}/subnet/{}` gained an optional `instances` response property: a list of `{id, ipv4}` attachment entries naming the instances bound to the subnet and their leased addresses. Tolerated today by `extra="allow"`, but it is the natural read-side counterpart to the `attach`/`detach` ops the connector already ships, so model it on `VpcSubnet` as a typed list. Affects `src/exoscale_connector/resources/vpc.py`, `docs/asset-types/vpc.md` | drift #57 | ~0.5h |
| **DBaaS `database` sub-resource** — `POST`/`GET`/`DELETE /dbaas-{pg,mysql}/{service-name}/database[/{database-name}]`. The client creates DBaaS **users** but has no way to create a **database** inside a service, so a provisioned pg/mysql service cannot be finished through the connector alone. Engine-generic in shape (pg + mysql today), so model it like the existing user methods rather than per-engine. Affects `src/exoscale_connector/resources/dbaas.py`, `docs/asset-types/dbaas.md` | coverage audit 2026-08-31 | ~3–4h |
| **DBaaS CA certificate** — `GET /dbaas-ca-certificate`. The CA bundle needed to TLS-verify a connection to a DBaaS service. Direct counterpart to the shipped `get_connection_info()`, which today hands back a host/port the caller has no supported way to verify. Single read endpoint, no live provisioning needed to exercise | coverage audit 2026-08-31 | ~1h |
| **SKS deprecated-resources pre-upgrade check** — `GET /sks-cluster-deprecated-resources/{id}`: "resources that are scheduled to be removed in future kubernetes releases". The missing safety step next to the already-complete SKS cluster/nodepool lifecycle — read-only, and the natural thing to call before a version upgrade. Affects `src/exoscale_connector/resources/sks.py`, `docs/asset-types/sks.md` | coverage audit 2026-08-31 | ~1h |
| **DBaaS service logs + metrics** — `POST /dbaas-service-logs/{service-name}` and `POST /dbaas-service-metrics/{service-name}`. Engine-generic observability reads (POST-with-body despite being reads), so one pair of methods serves every engine. Affects `src/exoscale_connector/resources/dbaas.py` | coverage audit 2026-08-31 | ~2h |
| **IAM organization policy** — `GET`/`PUT /iam-organization-policy` plus `POST /iam-organization-policy:reset`. Org-level policy sitting directly alongside the modelled `/iam-role` and the IAM policy cookbook (the one area the README claims real depth in). **Scope call needed first:** the out-of-scope list excludes `/organization`, which is a *different* path — this family has never actually been ruled on either way. `:reset` is destructive at org scope, so gate it like the other dangerous verbs and keep it off the CLI. Affects `src/exoscale_connector/resources/iam_role.py` or a new module, `docs/iam-policy-cookbook.md` | coverage audit 2026-08-31 | ~2–3h |
| **Typed-field gaps on shipped models** — response fields present in the spec but absent from the pydantic models, so they are reachable only untyped via `extra="allow"`. The substantive ones: `Instance` (`anti-affinity-groups`, `elastic-ips`, `private-networks`, `ssh-keys`, `user-data`, `public-ip-assignment`, `mac-address`, `disk-encrypted`, `secureboot-enabled`, `tpm-enabled`), `SksCluster` (`oidc`, `feature-gates`, `level`, `enable-kube-proxy`), `InstancePool` (`elastic-ips`, `ssh-keys`, `user-data`, `min-available`), `PrivateNetwork` (`leases`, `options`, `vni`), `LoadBalancerService` (`healthcheck`, `healthcheck-status`). Full list: `python scripts/model_schema_drift.py --summary .github/upstream/openapi-v2.json`. Curate rather than model wholesale — the models are a deliberate subset (see the developer guide) | coverage audit 2026-08-31 | ~3–4h |
| **DBaaS engine-specific tail** — pg `connection-pool` (`POST`/`GET`/`PUT`/`DELETE /dbaas-postgres/{}/connection-pool[/{name}]`), pg `user/{}/allow-replication`, pg `{service}/upgrade-check`, mysql `enable/writes`. Genuinely per-engine, so these do *not* collapse into generic methods the way settings/acl/maintenance did | coverage audit 2026-08-31 | ~3–4h |
| **DBaaS Kafka sub-resources** — `topic/acl-config[/{acl-id}]`, `schema-registry/acl-config[/{acl-id}]`, `connect/password/reveal`. Kafka-only; verify the engine is enabled on the test tenant **before** committing to this row (D4 — ClickHouse was retired for exactly this reason) | coverage audit 2026-08-31 | ~3–4h |
| **DBaaS migration family** — `/dbaas-{pg,mysql,valkey}/{}/migration/stop`, `GET /dbaas-migration-status/{name}`, `GET /dbaas-task-migration-check/{service}`, `GET /dbaas-task/{service}/{id}`. Coherent as one unit; `dbaas-task` is the generic async-task read the others report through | coverage audit 2026-08-31 | ~2–3h |
| **DBaaS external endpoints + integrations** — ~15 paths: `/dbaas-external-endpoint-{datadog,prometheus,rsyslog,elasticsearch,opensearch}`, `/dbaas-external-endpoint/{}/attach\|detach`, `/dbaas-external-endpoint-types`, `/dbaas-external-endpoints`, `/dbaas-integration[-types,-settings]`, `/dbaas-external-integration*`. Log/metric shipping to third-party observability. Largest single item here and the least core to provisioning — the obvious first thing to descope if 0.7.0 runs long. Needs a scope call under D4: several endpoint types may not be enabled on a default tenant | coverage audit 2026-08-31 | ~8–12h |

_Running total: ~3 days (~25h) — past the ~8–16h graduation window.
**Graduated into milestone 0.6.0 as two issues:** KMS as its own issue (large,
self-contained), and the rest (VPC, DBaaS version params, nvidia-mig,
ClickHouse, deploy targets, events, full SG rule-reference typing) as one
batched issue. Estimates are first-pass, refined per drift during Claude Code
evaluation._

_**Batched issue (#45) implemented** on `feat/additive-apiv2-batch`: VPC
(+subnets/routes/attach-detach), full SG rule-reference typing, deploy targets
(+instance wiring), events, generic DBaaS settings/acl/maintenance, first-class
DBaaS `version`, and SKS `nvidia-mig-profiles` — unit-tested, `ruff`/`mypy`/llms
`--check` green; live verification per docs/live-test-plan.md and merge pending.
KMS (#44) still open._

_Post-graduation running total: **~29–38h (~4–5 days)** — well past the ~8–16h
graduation window. **Graduated into milestone 0.7.0 as one batched issue**, per
D3 and because no single row is large and self-contained the way KMS was in
0.6.0. Rough tiers, in the order they should be tackled and descoped:_

| Tier | Rows | Estimate |
|---|---|---|
| **A — core gaps** | DBaaS `database`, DBaaS CA certificate, SKS deprecated-resources, DBaaS logs/metrics, IAM organization policy | ~9–11h |
| **B — typed-field gaps** | Unmodelled response fields on shipped models | ~3–4h |
| **C — tail** | DBaaS engine-specific, Kafka sub-resources, migration family, external endpoints/integrations | ~16–23h |
| **carried** | VPC subnet `instances` list (drift #57) | ~0.5h |

_Tier C is the descope valve: external endpoints/integrations alone is ~8–12h
and the least core to provisioning. Two rows (IAM organization policy, external
endpoints) need a **scope call before implementation**, not after._

_**Where the tier A/B/C rows came from — and the process gap they expose (D5).**
Not from drift. The backlog above them is drift-fed, and the weekly watch only
ever reports what *changed* since the accepted snapshot; APIv2 surface that has
been present all along and was simply never modelled is invisible to it
permanently, and is not on the out-of-scope list either. So a quiet drift queue
never meant coverage was complete. These rows came from auditing the committed
snapshot directly (261 paths, subtracting everything reachable via the
engine-generic `dbaas-{type}/…` interpolation, the mixins, and the documented
out-of-scope list). Worth repeating periodically rather than never — it is
offline work against `.github/upstream/openapi-v2.json`, needs no network, and
`scripts/model_schema_drift.py --summary` already covers the field-level half._

_**Unchanged by drift #71** (2026-08-13): every change in that run landed on
ClickHouse or `/ai/*`, both already out of scope, so nothing was harvested — see
the out-of-scope list._

_drift #57 note: the delete-user change was the first breaking-*shaped* drift
that unit CI cannot catch — a path parameter, not a model field, so
`test_model_schema_drift.py` stays green either way. That class of drift is only
findable by reading the path diff, which is worth remembering for future
triage even now that ClickHouse itself is out of scope._

_**Both ClickHouse rows retired 2026-08-01 — see D4.** Live verification was
attempted and blocked: `POST /dbaas-clickhouse/{name}` and even the read-only
`GET /dbaas-settings-clickhouse` return `403 "... not enabled"`, i.e. tenant
product enablement rather than an IAM role gate (that reads `Forbidden by role
policy for ...`). Plan discovery via `GET /dbaas-service-type` succeeds and
lists ClickHouse with 112 plans, so it gives a false green — do not read it as
the engine being usable. Since the engine cannot be enabled, exercised, or
verified on a default tenant, ClickHouse moved to the out-of-scope list rather
than staying as permanently-blocked backlog. Nothing was provisioned and no cost
was incurred. The 403 diagnostic and skip policy stay recorded under tier 4 in
`docs/live-test-plan.md` — they generalise to any opt-in product._

_drift #43 note: the earlier InstancePool `error-reason` + `error`-state item
(harvested from drift #40) was **retracted** — #43 reverses it upstream,
removing `error-reason` from the instance-pool / load-balancer-service responses
and dropping the `error` enum value from `state`. Nothing was ever modelled, so
no code change is needed; the item is simply gone._

### Deliberately out of scope (do not re-harvest from drift)

These APIv2 asset types exist but are intentionally not modelled. Drift triage
should **not** keep re-adding them to the backlog:

- **`/organization`** — org/account management, out of the connector's remit.
- **`/quota`** — account limits; read-only account metadata, not provisioning.
- **`/usage-report`, `/live-balance`, `/env-impact`, `/environmental-impact/*`,
  `/sos-buckets-usage`** — billing/usage reporting, not the connector's job.
  (`/sos-buckets-usage` was ruled out here on 2026-08-31 during the coverage
  audit: it is per-bucket usage accounting, the same family and the same verdict
  as the rest of this row. Reverse it if usage reporting ever becomes in scope —
  it is one read endpoint.) (`#57` added
  `POST /environmental-impact/estimate` and `GET /environmental-impact/report`
  alongside the older `/env-impact/{period}`; same family, same verdict.)
- **`/console`** — instance web-console access; interactive, not automation.
- **`/dbaas-clickhouse/*` (ClickHouse DBaaS engine)** — not enabled on a default
  tenant (`403 "... not enabled"` on every operation, read-only ones included),
  so it cannot be exercised or verified here at all. Per D4 that makes it niche
  and out of scope. Note this does *not* remove anything shipped: the generic
  `get_settings` / `get_acl_config` / `start_maintenance` methods that came out
  of the drift #43 ClickHouse row are engine-agnostic and serve pg, mysql,
  valkey and the rest. `DBaaSServiceClient` still accepts
  `service_type="clickhouse"` — it is simply unsupported and unverified, and
  `delete_user` carries a docstring warning about the upstream
  `{username}` → `{user-uuid}` path change (drift #57) for anyone who tries.
  Drift #71 grew the engine again — a role sub-resource
  (`GET /dbaas-clickhouse/{}/role`, `DELETE .../role/{role-uuid}`, with four new
  `dbaas-clickhouse-role*` schemas) plus a `tiered_storage_move_factor` key in
  the `clickhouse-settings` schema. Nothing harvested, per D4. The engine-generic
  test from the #43 row was re-run before deciding: `/role` appears under
  `/dbaas-clickhouse/` and nowhere else in the spec (`/iam-role` is unrelated),
  so unlike settings/acl/maintenance it is genuinely ClickHouse-only and there is
  no generic method hiding inside it.
- **`/ai/*` (AI / GPU inference)** — deferred: the product surface is new and
  still churning (it moved again in #43, in #52 — `POST`/`PATCH /ai/api-key`
  tightened `name` to a 1–50 char pattern and `POST /ai/deployment` gained
  `product-name` — again in #57, where `GET /ai/deployment` gained an
  optional `visibility` query parameter, and again in #71, where
  `inference-engine-version` moved its default `0.25.1` → `0.26.0` and added the
  matching enum value on request and response). Revisit once it stabilises.
  The #71 response-side enum addition is the only warning-level change oasdiff
  has raised here so far; it is harmless because `/ai/*` is unmodelled, and the
  D3 `Literal`-pin edge case still only applies to `iam_role.py`.

---

## Decisions

### D1 — Advisor, not operator (2026-06-10)
The AI layer targets the *learning* path, not the execution path.

Rationale: infrastructure execution should be deterministic — scripts,
schedulers, desired-state reconciliation; an LLM in that loop adds variance
exactly where variance is the enemy, and burns tokens on every run for
something that should cost nothing after the first time. The advisor instead
produces durable artifacts (reviewed, committed, re-runnable scripts —
idempotent via `ensure()`) and a more capable engineer: the AI's job ends at
the moment of understanding. Consequences: rung 3 is read-only by
construction; no agent-orchestration features in the connector; anything
AI-flavored beyond generated docs lives outside this repo.

### D3 — Drift triage: breaking fixes now, additive batches by effort (2026-06-22)
Every `upstream-drift` issue is evaluated with Claude Code when it lands, and
each change is sorted into one of three buckets:

- **Breaking → fix now, own PR.** Renamed/removed/retyped/newly-required request
  fields (turns `test_model_schema_drift.py` red). Edge case: a new enum value on
  a field pinned with `Literal` is also breaking — `iam_role.py` is the only such
  model today, so plain-`str` enum additions elsewhere are tolerated/additive.
- **Doc-gotcha invalidation → fix now, trivial.** A drift that makes a documented
  gotcha wrong (changed default, an "always null" field that starts returning
  data) without breaking a model. Correcting misinformation is cheaper than
  carrying it; it does not wait in the backlog.
- **Additive → backlog above, batched.** New optional first-class params, new
  endpoints, new asset types. Harvested into the backlog table before the drift
  issue is closed (the snapshot refreshes on every run, so unharvested additive
  content is lost otherwise).

**Graduation is effort-based, not count- or time-based.** Each additive item gets
a rough impl + full-test-run estimate during evaluation. When the accumulated
backlog crosses ~8–16h (1–2 days), it graduates as a single GitHub issue on the
active milestone and is implemented in one focused session. Rationale: no
appetite for tiny per-drift updates; breaking changes stay immediate while
additive work accrues until it justifies a session, keeping GitHub clean and
matching this file's "one heading = one issue, graduate when ripe" model.

### D4 — Default-enabled products only (2026-08-01)
If a product is not enabled on a default Exoscale tenant, it is out of scope.
Opt-in products are niche by definition, and this is a hobby project with
finite appetite.

Rationale: the connector's value is verified knowledge — every asset page
carries live-verified gotchas, and D1 makes the live API the arbiter whenever
the spec and reality disagree. A product that cannot be enabled cannot be
exercised, so it can only ever be modelled *from the spec* — precisely the
thing D1 says not to trust. Shipping unverifiable surface trades the repo's
main promise for coverage nobody asked for. ClickHouse is the worked example:
it reached the backlog through two drift issues, survived a full triage cycle,
and only revealed itself as unusable when a live run hit
`403 "... not enabled"` on even its read-only endpoints (2026-08-01).

Consequences:

- Drift triage does **not** harvest opt-in products into the backlog. When a
  drift lands on one, record it on the out-of-scope list and move on — the same
  treatment `/organization` and `/ai/*` already get.
- Probe cheaply before committing effort. A read-only call on the product is
  enough, and it is the reliable signal: a tenant enablement gate rejects reads
  as well (`... not enabled`), whereas an IAM role gate reads `Forbidden by role
  policy for ...`. Catalogue endpoints are *not* a signal —
  `GET /dbaas-service-type` cheerfully lists ClickHouse plans on a tenant that
  cannot use the engine.
- **Already-shipped clients stay.** This governs what gets harvested from here
  on, not a demolition order. `VpcClient` shipped in 0.6.0 and VPC is itself a
  per-account product (tier-1 live tests skip on its 403) — it stays: the code
  exists, is unit-tested, and removing it would be pure churn. KMS is a
  different case again — it is blocked by role policy, not enablement, so D4
  does not touch it.
- Nothing is removed from `DBaaSServiceClient` for ClickHouse. Engine-generic
  methods still accept the type; it is unsupported and unverified, not
  amputated.

### D5 — Coverage is audited periodically, not inferred from a quiet drift queue (2026-08-31)

The additive backlog is **drift-fed**: rows arrive from the weekly
`upstream-drift` watch, which reports only what *changed* since the last
accepted snapshot. That makes it structurally blind to APIv2 surface that has
been present all along and was simply never modelled — such surface never
appears in a diff, so it can never enter the backlog, and unless someone rules
on it, it is not on the out-of-scope list either. An empty drift queue therefore
says "nothing moved upstream", never "coverage is complete". Reading it as the
latter is the mistake this decision exists to prevent.

So: audit coverage directly against the committed snapshot from time to time
(release boundaries are the natural cadence), independently of drift. It is
offline work — no network, no tenant, no cost:

- **Path-level.** Enumerate `paths` in `.github/upstream/openapi-v2.json` and
  subtract what the connector reaches. Beware the obvious shortcut: grepping
  `src/` for a path family **over-reports gaps badly**, because the DBaaS
  engines are never spelled literally — `dbaas.py` interpolates
  `f"dbaas-{self._url_type(service_type)}/…"`, so `/dbaas-mysql`, `/dbaas-kafka`
  and friends look unmodelled while being fully covered. Same for the mixins
  (`_reverse_dns.py`) and the SKS sub-resource endpoints. Resolve how a path is
  *constructed* before calling it a gap.
- **Field-level.** `python scripts/model_schema_drift.py --summary
  .github/upstream/openapi-v2.json` already prints unmodelled optional fields per
  model. They are informational by design (`extra="allow"`), but the list mixes
  incidental fields with substantive ones — curate, do not model wholesale.

The 2026-08-31 audit that produced the tier A/B/C rows found ~29–38h of
unmodelled surface behind a drift queue that had been quiet since #71.

### D2 — Catalogue knowledge is discovered, never hardcoded (2026-06-10)
No enums of zones, instance types, families/sizes, templates, or DBaaS plans
in the package. The live API is the catalogue (`ZoneClient`,
`InstanceTypeClient`, `TemplateClient`, `list_service_types`); helpers
resolve human forms (`standard.tiny`) against live data and return `None` /
server errors rather than validating against stale lists. `KNOWN_ZONES`
remains a hint for error messages only.
