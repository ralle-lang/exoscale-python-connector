# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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

[Unreleased]: https://github.com/ralle-lang/exoscale-python-connector/compare/v0.6.0...HEAD
[0.6.0]: https://github.com/ralle-lang/exoscale-python-connector/compare/v0.5.0...v0.6.0
[0.5.0]: https://github.com/ralle-lang/exoscale-python-connector/compare/v0.4.0...v0.5.0
[0.4.0]: https://github.com/ralle-lang/exoscale-python-connector/compare/v0.3.0...v0.4.0
[0.3.0]: https://github.com/ralle-lang/exoscale-python-connector/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/ralle-lang/exoscale-python-connector/releases/tag/v0.2.0
