# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.6.2] - 2026-10-08

Bug-fix release resolving the medium-severity findings of the 2026-09-16
codebase audit. Three fixes change behaviour you may notice:

- DBaaS create/update, the user and maintenance methods, and `delete` now
  **wait** for their operation by default (pass `wait=False` to opt out).
- An unrecognised `EXOSCALE_VERIFY_TLS` value now **raises** `ConfigError`
  instead of silently disabling TLS verification.
- `exoscale-snapshot` and `exoscale-block-volume-snapshot` no longer offer
  `create`, which could only fail.

Additive: `IAMAssumeRolePolicy`, `wait=` on the DBaaS user/maintenance
methods, `--file` on `dbaas`/`kms create`, and `verbs=` on `run_resource_cli`.

### Fixed
- **`DnsDomainClient.ensure()` works.** It always raised `ValueError`
  because its snake_case `name_field` was looked up in the kebab-case
  payload (#106).
- **A blank `EXOSCALE_VERIFY_TLS` no longer disables TLS verification.**
  Unset or empty now keeps verification on, `false`/`0`/`no`/`off` turn it
  off, and an unrecognised value raises `ConfigError` instead of failing
  open (#107).
- **Block volume `resize()` no longer polls the volume id as an operation.**
  The spec has `:resize-volume` return the volume itself; that body now
  yields a settled `Operation` referencing the volume. Spec-based; not
  live-verified (#109).
- **`SksCluster.service_level` maps to the API's `level` field.** It used
  the wire name `service-level`, so reads always returned `None` and
  model-built create payloads omitted the required `level`. Model-built
  payloads also no longer send an empty read-only `nodepools` list (#110).
- **IAM assume-role policies use the spec shape.** `assume_role_policy` was
  typed as the per-service `IAMPolicy`, but the API defines a flat
  `{"rules": [...]}`, so reads were empty and the typed helpers built an
  undefined body. New `IAMAssumeRolePolicy` (with `with_rules()`);
  `set_assume_role_policy()` takes it or a dict (#111).
- **DBaaS mutations await their operation.** Create/update, the user methods,
  `start_maintenance` and `delete` returned or discarded the operation the
  API answers with, so `wait=` was a no-op and failures never surfaced. They
  now await it by default (`wait=False` opts out); user/maintenance methods
  still return a dict, now the settled envelope (#112).
- **CLI errors no longer dump tracebacks.** Connection errors and timeouts, a
  missing or unreadable `--file`, and Ctrl-C now print a one-line `error:`
  message and exit 1 (130 for Ctrl-C), like API errors already did (#113).
- **`exoscale-dbaas create` and `exoscale-kms create` accept `--file`**
  (`-` = stdin) besides `--json`, so payloads with secrets such as
  `admin-password` no longer have to sit in the process list. The body
  stays optional (#114).
- **`exoscale-snapshot` and `exoscale-block-volume-snapshot` no longer offer
  `create`.** Neither collection supports POST, so the verb could only fail;
  snapshots are created from the instance or volume (#115).

## [0.6.1] - 2026-10-07

Bug-fix release from the 2026-09-16 codebase audit and the SDK 0.16.4 drift
triage. No breaking changes; the fixes add a few backward-compatible
extras (`signed=` on requests, `SksNodepoolTaint`, `IAMUser.pending`).

### Fixed
- **IAM user `get`, `create` and `update` work.** APIv2 has no
  `GET /user/{id}` (404 even for existing users, verified live), so `get()`
  always failed and `create()`/`update()` raised after succeeding.
  `IAMUserClient.get` now resolves from the list; `IAMUser` gains `pending` (#101).
- **VPC route create and subnet update no longer fail after succeeding.**
  Both return the resource directly (per the spec), but the connector treated
  the body as an operation and polled a non-existent operation id until it
  raised `NotFoundError`. They now return a settled `Operation` whose
  `reference_id` is the route/subnet id. Spec-based; not live-verified (#102).
- **Grafana DBaaS services can be read.** `DBaaSConnectionInfo.uri` was typed
  `List[str]`, but Grafana returns a single string, so `get()`, `create()`,
  `update()` and `get_connection_info()` raised for Grafana. It is now
  `Union[str, List[str]]` (#99).
- **Tainted SKS nodepools no longer break cluster reads.** `SksNodepool.taints`
  was typed `Dict[str, str]`, but each taint is a `{value, effect}` object, so
  one tainted pool made `get()`/`list()` raise for the whole zone. New
  `SksNodepoolTaint` model; `taints` is now `Dict[str, SksNodepoolTaint]` (#98).
- **Zone listing works with least-privilege keys.** `ZoneClient.list()` now
  sends `GET /zone` unsigned: the endpoint is public, but a signed request is
  checked against the key's IAM policy, so a restricted key got `403`. Mirrors
  the official SDKs. `ExoscaleClient.request()`/`get()` gain `signed=` (#92).
- **Operation waits survive a transient 429/5xx poll.** `wait_operation()`
  aborted on the first rate-limited or 5xx `GET /operation/{id}`, although the
  mutation was still running server-side. Retryable statuses now count against
  `max_poll_failures` like connection drops; other errors still surface at
  once (#93).

## [0.6.0] - 2026-07-08

Additive APIv2 coverage — new asset types and typed-coverage gaps surfaced by the
upstream-drift triage. Purely additive: no existing behaviour changes.

### Added
- **VPC asset type** (`VpcClient`) — `/vpc` with nested `subnet` and `route`
  sub-resources, plus instance ↔ subnet `attach`/`detach`. Models `Vpc` /
  `VpcSubnet` / `VpcRoute`; `exoscale-vpc` CLI; doc page (#45).
- **KMS asset type** (`KmsKeyClient`) — the full `/kms-key` surface (15
  endpoints): CRUD, enable/disable, key rotation, envelope crypto
  (`encrypt` / `decrypt` / `re_encrypt` / `generate_data_key`), the scheduled
  deletion lifecycle, and multi-zone replication. Crypto operations are
  library-only (secret-bearing, kept off the CLI); there is no immediate delete,
  so `delete()` raises in favour of `schedule_deletion()`. `exoscale-kms` CLI
  exposes the management verbs; doc page (#44).
- **Deploy targets** — read-only `DeployTargetClient` (`/deploy-target`);
  `Instance.deploy_target` lets a create pin an instance to a placement target
  (#45).
- **Audit events** — read-only `EventClient` over `/event`, with `from_`/`to`
  windowing (#45).
- **Typed security-group rule references** — a rule's `security_group` is now a
  `SecurityGroupResource` (`id` / `name` / `visibility`) instead of a bare
  id-only reference, so both private peers and Exoscale-managed public groups are
  typed on request and round-tripped on response (#45).
- **DBaaS** — a first-class typed `version` field, plus engine-generic
  `get_settings` / `get_acl_config` / `start_maintenance` methods (#45).
- **SKS** — nodepool `nvidia_mig_profiles` (#45).

### Changed
- Docs: the SOS bucket endpoint format (`https://sos-<zone>.exo.io`, auto-derived
  from the zone) is now surfaced in the README and user guide, not only the
  object-storage asset page (#32).

## [0.5.0] - 2026-06-12

### Added
- **HTTP resilience hardening:** idempotent requests now retry connection-level
  transient failures (dropped connections, read timeouts, chunked-encoding
  errors) in addition to retryable HTTP statuses, on the same bounded
  jittered-backoff budget — closing the gap where a single TCP reset could abort
  a re-runnable provisioning script. The retryable status sets are configurable
  per client (`ClientConfig.retryable_statuses_idempotent` / `_mutating`), and
  `request(..., max_retries=)` overrides the budget for one call. `POST` is still
  never retried on a 5xx or a dropped connection, preserving the
  no-duplicate-mutation guarantee. The full policy is documented in the developer
  guide (#21).
- **Model↔spec field-drift gate:** `tests/unit/test_model_schema_drift.py` diffs
  every pydantic resource model against the committed OpenAPI snapshot and fails
  on renamed/removed/retyped fields and newly-required spec fields; intentional
  divergences live in a self-policing allowlist. The weekly drift workflow embeds
  the same diff against the incoming spec (#20).
- **Stability & compatibility policy** (developer guide): defines the public API
  — the exported Python symbols plus the `llms.txt` / skill bundle contract that
  the advisor consumes — what `0.x` version bumps mean, and the deprecation
  procedure. The README points to it rather than restating it.
- CI **`min-deps` job** installs the package against its declared *minimum*
  dependency versions (`ci/constraints-min.txt`) and runs the suite, so a too-low
  floor fails mechanically. `tests/unit/test_min_constraints.py` keeps the pins
  in lockstep with the `pyproject.toml` floors (a drifted/missing/stale pin fails).

### Changed
- **Release machinery hardened:** every GitHub Action across all workflows is now
  pinned to a full commit SHA, and PyPI publishing emits PEP 740 build
  attestations explicitly. Publishing already used Trusted Publishing (OIDC) with
  no stored token; the tag-to-publish flow is now documented in the developer
  guide (#24).
- **Breaking:** raised the `requests` floor from `>=2.28` to `>=2.30`. The old
  floor was never a real lower bound — the test suite cannot run at it (the
  `responses` harness requires `requests>=2.30`). Consumers on any recent
  `requests` need no change.

## [0.4.0] - 2026-06-12

### Changed
- Upstream drift watch now maps a spec change to the **affected connector
  modules** (`scripts/drift_operations.py`), so the weekly drift issue names
  which modules to review instead of dumping the whole mapping table. The
  module → operations map is self-enforcing: `test_drift_operations.py` fails if
  the code calls an endpoint outside a module's collection path that isn't
  declared.

### Documentation
- SKS asset page now lists the valid cluster/nodepool `addons` values, **derived
  automatically from the committed OpenAPI spec** by `generate_llms_txt.py` (a
  marker-fenced, generated block) rather than hand-maintained. Addons are a
  spec-only enum with no runtime list endpoint, so this keeps them honest: the
  upstream drift watch refreshes the spec, the generator re-injects, and the
  `--check` gate enforces sync (#16).
- instance-pool asset page now documents `anti_affinity_groups` — the model
  block, a create example, and a gotcha explaining it spreads pool members
  across distinct hosts and is create-only. Previously invisible to readers
  (and to LLMs reading the page), which led to the wrong conclusion that pools
  can't guarantee host spread (#13).

### Added
- `SksClusterClient.list_versions()` — discover the Kubernetes versions a new
  SKS cluster may use (wraps `GET /sks-cluster-version`). Lets callers ground a
  cluster's `version` against what the API currently accepts instead of
  hardcoding a literal like `"1.30"` that breaks once Exoscale retires it.
  Mirrors `DBaaSServiceClient.list_service_types()` (#14).
- `PrivateNetworkClient.attach_instance()` / `detach_instance()` — join and
  remove compute instances to/from a private network (the colon-actions
  `PUT private-network/{id}:attach` / `:detach`), with an optional static `ip`
  lease for managed networks. Closes the gap where the connector could create a
  private network but not actually wire instances into it (#12).
- `DBaaSService.ip_filter` — typed field (`List[str]` of CIDRs) for the DBaaS IP
  allow-list. Settable via the create/update payload and read back from the
  type-specific GET. Since a managed DB can't join a private network, this plus
  TLS is the primary way to secure it (#15).

## [0.3.0] - 2026-06-11

### Added
- AI reference bundle `docs/llms.txt` — a single self-contained context file
  (introspected API surface plus every asset-type page with its live-verified
  gotchas) to paste into an LLM for accurate, method-citing guidance. Sync with
  the code is enforced by CI.
- Packaged editor skill shipped in the wheel (`exoscale_connector/_skill/`) and
  installable into a project's `.claude/skills/` via
  `exoscale-connector skill install`, so the same reference answers questions
  ambiently during normal work.
- Upstream drift watch (weekly CI) — diffs the Exoscale APIv2 OpenAPI spec
  against a committed snapshot and watches the official SDK's PyPI version,
  filing agent-ready drift issues automatically.

## [0.2.0] - 2026-06-11

### Added
- Initial public release: a clean, typed, reusable Python connector for the
  Exoscale APIv2 (requests + pydantic only) — per-asset-type clients and
  models, an umbrella CLI plus thin per-asset CLIs, and IAM policy expression
  helpers.

[Unreleased]: https://github.com/ralle-lang/exoscale-python-connector/compare/v0.6.2...HEAD
[0.6.2]: https://github.com/ralle-lang/exoscale-python-connector/compare/v0.6.1...v0.6.2
[0.6.1]: https://github.com/ralle-lang/exoscale-python-connector/compare/v0.6.0...v0.6.1
[0.6.0]: https://github.com/ralle-lang/exoscale-python-connector/compare/v0.5.0...v0.6.0
[0.5.0]: https://github.com/ralle-lang/exoscale-python-connector/compare/v0.4.0...v0.5.0
[0.4.0]: https://github.com/ralle-lang/exoscale-python-connector/compare/v0.3.0...v0.4.0
[0.3.0]: https://github.com/ralle-lang/exoscale-python-connector/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/ralle-lang/exoscale-python-connector/releases/tag/v0.2.0
