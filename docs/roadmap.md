# Roadmap

Forward-looking plans and the reasoning behind them. Work items are written
issue-ready (one heading = one GitHub issue); the **Decisions** section records
the "why" so it survives even after issues are closed.

How we track: this file holds direction and rationale; GitHub issues/milestones
hold execution state. When an item graduates to an issue, link it here.

---

## Milestone: v0.2.0 — verified extensions

Everything on `fix/assessment-findings` and `feat/connector-extensions`,
validated against a live tenant and released.

### Run live verification for the fix + extensions branches
Run the tier suite (0 → 4) against the test tenant with `EXOSCALE_RECORD=1`.
Focus areas — the endpoints implemented from the API reference without live
evidence yet (all marked "pending live verification" in code and docs):
reverse DNS (`/reverse-dns/{kind}/{id}`), instance `:scale`, DBaaS
`update`/user endpoints, template register/delete, SOS object operations.
Fix any spec-vs-reality divergences found and record them in the asset pages'
Gotchas sections, per house convention.

### Seed the recorded-fixture archive
First `EXOSCALE_RECORD=1` run produces `tests/recorded/*.jsonl`. Review for
tenant identifiers, commit, and confirm `test_recorded_replay.py` exercises
them in CI from then on.

### Merge to main, bump version, tag v0.2.0
Merge both branches after verification (user-gated), bump `pyproject.toml` +
`__version__`, tag. The release workflow builds and publishes.

### Configure PyPI trusted publishing
Register the repo + `release.yml` as a trusted publisher for
`exoscale-connector` on pypi.org and create the `pypi` GitHub environment.
The workflow is already in-repo and inert until this is done.

---

## Milestone: Advisor — AI-assisted *learning*, not operation

An aid for people who don't know Exoscale or this connector yet: natural
language in, **explained code out, human executes**. See Decisions below for
why there is deliberately no AI execution layer. Rungs are ordered by
value-per-effort; each stands alone.

### Rung 1 — generated AI-ready reference bundle (`docs/llms.txt`)
A docs build step that generates one self-contained context file from ground
truth: the introspected API surface (every `ResourceClient` subclass, method
signatures, pydantic model fields — generated from code so it cannot drift)
plus the distilled asset-type pages with their live-verified gotchas. A
newcomer pastes it into whatever LLM they already use and gets accurate,
hallucination-free guidance citing real methods. No runtime AI, no new
dependencies; CI check that the bundle is in sync with the code. Lives in
this repo.

### Rung 2 — editor/assistant skill packaging
Package the rung-1 bundle as a skill for AI-assisted editors (e.g. a Claude
Code skill), so "how do I give this instance more memory?" gets answered
ambiently from verified docs during normal work. Thin wrapper around rung 1.

### Rung 3 — read-only advisor MCP server (separate repo)
An MCP server exposing docs search plus *list-only* live catalogue queries
(zones, instance types, templates) — so the advisor can answer "what exists
in de-fra-1 right now" with live data while being structurally incapable of
mutation. **Separate repository** (`exoscale-mcp-advisor` or similar): it
adds an MCP framework dependency and a different risk/release profile, and
the connector's "requests + pydantic only" promise must hold. No mutation
tools, by design, ever — see Decisions.

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
