# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- `PrivateNetworkClient.attach_instance()` / `detach_instance()` — join and
  remove compute instances to/from a private network (the colon-actions
  `PUT private-network/{id}:attach` / `:detach`), with an optional static `ip`
  lease for managed networks. Closes the gap where the connector could create a
  private network but not actually wire instances into it (#12).

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

[Unreleased]: https://github.com/ralle-lang/exoscale-python-connector/compare/v0.3.0...HEAD
[0.3.0]: https://github.com/ralle-lang/exoscale-python-connector/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/ralle-lang/exoscale-python-connector/releases/tag/v0.2.0
