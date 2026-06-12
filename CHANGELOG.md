# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- **Stability & compatibility policy** (developer guide): defines the public API
  — the exported Python symbols plus the `llms.txt` / skill bundle contract that
  the advisor consumes — what `0.x` version bumps mean, and the deprecation
  procedure. The README points to it rather than restating it.
- CI **`min-deps` job** installs the package against its declared *minimum*
  dependency versions (`ci/constraints-min.txt`) and runs the suite, so a too-low
  floor fails mechanically. `tests/unit/test_min_constraints.py` keeps the pins
  in lockstep with the `pyproject.toml` floors (a drifted/missing/stale pin fails).

### Changed
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

[Unreleased]: https://github.com/ralle-lang/exoscale-python-connector/compare/v0.4.0...HEAD
[0.4.0]: https://github.com/ralle-lang/exoscale-python-connector/compare/v0.3.0...v0.4.0
[0.3.0]: https://github.com/ralle-lang/exoscale-python-connector/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/ralle-lang/exoscale-python-connector/releases/tag/v0.2.0
