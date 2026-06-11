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
`0.2.0`. Tag creation pending PyPI trusted-publishing setup (issue #4).

### Configure PyPI trusted publishing (issue #4 — user task)
Register the repo + `release.yml` as a trusted publisher for
`exoscale-connector` on pypi.org and create the `pypi` GitHub environment.
The workflow is already in-repo and inert until this is done. Once done,
push the `v0.2.0` tag to trigger the release workflow.

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
mutation. **Separate repository** (`exoscale-mcp-advisor` or similar): it
adds an MCP framework dependency and a different risk/release profile, and
the connector's "requests + pydantic only" promise must hold. No mutation
tools, by design, ever — see Decisions.

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
  into shell), then commit the refreshed snapshot in the same run.
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

## Backlog / deferred

### Async client (httpx) — deferred, decision pending
Doubles the maintenance surface and strains the "self-contained, requests +
pydantic" portability promise. Revisit only with a concrete consumer that
needs high-concurrency fan-out; would likely live as an optional extra or
sibling package.

### Size-ordering / scale-to-slug helpers — declined for now
A `scale_to_slug()` or "next size up" helper implies a size-ordering table in
the package; catalogue knowledge stays server-side (discovered, never
assumed). Callers can derive ordering from the numeric `cpus`/`memory`
fields. Reopen if a real consumer needs it badly enough to justify the
maintenance trap.

### Pagination support — contingent on the API
APIv2 list endpoints are unpaginated today; `ResourceClient.list()` documents
that assumption. If Exoscale introduces cursors, `list()` grows cursor
handling. Nothing to do until then.

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

### D2 — Catalogue knowledge is discovered, never hardcoded (2026-06-10)
No enums of zones, instance types, families/sizes, templates, or DBaaS plans
in the package. The live API is the catalogue (`ZoneClient`,
`InstanceTypeClient`, `TemplateClient`, `list_service_types`); helpers
resolve human forms (`standard.tiny`) against live data and return `None` /
server errors rather than validating against stale lists. `KNOWN_ZONES`
remains a hint for error messages only.
