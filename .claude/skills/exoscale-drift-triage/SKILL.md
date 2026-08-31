---
name: exoscale-drift-triage
description: >-
  Use to triage upstream-drift issues in the exoscale-connector repo — the
  weekly upstream-drift workflow files them when the APIv2 OpenAPI spec or the
  official exoscale SDK changes. Walks: find the open issue, read its prepared
  analysis, classify each change as breaking-fix-now or additive-roadmap, then
  produce a branch + PR (breaking) or roadmap entry (additive), comment the
  decision, and stop at the human gate before merge/push/pull. Also covers the
  proactive half: when no drift issue is open, run the offline coverage audit of
  the committed APIv2 snapshot — an empty drift queue means nothing moved
  upstream, not that coverage is complete.
---

# exoscale-connector drift triage

The `upstream-drift` workflow (`.github/workflows/upstream-drift.yml`) runs
Mondays and files/updates a single open issue per source, labelled
`upstream-drift`, with one of these titles:

- `Upstream drift: APIv2 OpenAPI spec changed`
- `Upstream drift: new official exoscale SDK release on PyPI`

The issue body already contains the analysis: an evaluation checklist, an
**Affected connector modules** map, a **Model ↔ spec field drift** table, and
the oasdiff changelog. Don't redo that work by hand — but don't treat it as the
whole picture either. **It describes the spec as of the bot's run, not as of
now.** Anything that landed upstream afterwards is absent from the issue, and
the changelog will still claim `0 error, 0 warning`. Read the analysis, then
verify it against the live spec in step 3; where they disagree, the live spec
wins. Drift #57 reported 5 informational changes and omitted a breaking path
rename that arrived days later.

The committed snapshots under `.github/upstream/` are **not** touched by the
bot — main is protection-ruled, and per D1 the baseline should move only once a
human has accepted the drift. You advance them yourself as the final part of
triage, inside the reviewed triage PR (step 7). Until then the committed
snapshot is the pre-change baseline, so fetch the current spec to a temp file
for the ground-truth checks (step 3).

## Governing decisions (do not override)

- **D1 — never auto-fix.** A spec diff is a prompt for human+agent review, not
  ground truth. The live API and the verified gotchas win over the spec.
- **D3 — classify, then route.** Breaking → fix now on a branch. Additive →
  record in `docs/roadmap.md` backlog, batched; graduate a batch to an issue at
  ~8–16h estimated effort.
- **D5 — coverage is audited, never inferred from a quiet queue.** The backlog
  is drift-fed and the watch reports only what *changed*. Surface that was never
  modelled cannot appear in a diff, so it never enters the backlog and is not on
  the out-of-scope list either. Audit the snapshot directly at release
  boundaries. See the coverage-audit section below.
- **D4 — default-enabled products only.** A product that is not enabled on a
  default tenant is out of scope: it cannot be exercised, so it could only ever
  be modelled from the spec — exactly what D1 forbids trusting. Do **not**
  harvest opt-in products into the backlog; add them to the roadmap's
  out-of-scope list instead. This governs new harvesting only — already-shipped
  clients (e.g. `VpcClient`, itself a per-account product) stay.

## Procedure

1. **Find work.**
   `gh issue list --label upstream-drift --state open`.
   None → **do not stop there.** An empty queue means "nothing moved upstream",
   never "coverage is complete" (D5). Report no open drift, then offer the
   **coverage audit** below — that is where the standing gaps live.

2. **Read the prepared analysis** in the issue body — focus on the
   **Affected connector modules** and **Model ↔ spec field drift** sections.

3. **Confirm against ground truth** (don't trust the prose alone). First fetch
   the current spec to a temp file (the same source the bot diffed) — keep it
   out of the worktree, since `.drift/` is not git-ignored:
   ```
   SPEC="$(mktemp -d)/spec.json"
   curl -fsSL --retry 3 https://openapi-v2.exoscale.com/source.json | jq -S . > "$SPEC"
   ```
   - `python scripts/model_schema_drift.py --summary "$SPEC"` — any
     renamed/removed/retyped or newly-required field is breaking model drift
     (it turns `test_model_schema_drift.py` red once the snapshot advances);
     unmodelled optional fields are informational, tolerated by `extra="allow"`.
   - `python -m pytest tests/unit/test_model_schema_drift.py tests/unit/test_drift_operations.py`
   - **Diff the paths yourself** — this is the step that finds what the issue
     missed, and none of the checks above can substitute for it:
     ```
     python scripts/drift_operations.py --affected .github/upstream/openapi-v2.json "$SPEC"
     ```
     Added/removed/changed paths here but not in the issue means drift landed
     after the bot ran. A *removed* path paired with a similar *added* one is a
     rename — inspect both operations before concluding anything, since the
     operationId usually stays the same.
   - Re-read the gotchas on each affected `docs/asset-types/*.md` page; a spec
     change can invalidate a documented gotcha.

4. **Classify each change** per D3:
   - **Breaking** (red CI: rename/removal/retype/newly-required request field,
     or an invalidated gotcha) → fix now.
   - **Breaking but CI-invisible** — a **path or path-parameter** change
     (renamed/retyped path segment) on an endpoint the connector calls. Models
     are unaffected, so `test_model_schema_drift.py` stays green and
     `test_drift_operations.py` passes; nothing goes red while the call is
     broken at runtime. Step 3's path diff is the only thing that surfaces
     these. Treat as breaking, but see D1 before changing behaviour — if the
     endpoint cannot be live-verified, document the hazard rather than guessing
     at the new contract.
   - **Additive** (new optional fields, tolerated by `extra="allow"`; new
     endpoints/asset types not yet modelled) → roadmap.
   - **Out of scope** — the change belongs to an opt-in product (D4), or to an
     area already on the roadmap's out-of-scope list (`/organization`,
     `/ai/*`, billing/usage reporting, `/console`, ClickHouse). Record it on
     that list if it is new, and harvest nothing.

5. **Act — breaking (fix now):**
   - Branch: `git switch -c fix/drift-<short-topic>`.
   - Reconcile the model/docs; or, if the divergence is intentional and
     live-verified, record it in `ALLOWED_DIVERGENCES` (model drift) /
     `MODULE_SIBLING_OPERATIONS` (operations) with a reason.
   - Regenerate AI artifacts: `python scripts/generate_llms_txt.py`
     (then `--check` must pass — keeps llms.txt + both skill copies in sync).
     That gate covers a **chain**, not one file: two output copies
     (`src/exoscale_connector/_skill/`, `.claude/skills/exoscale-connector/`)
     **and** the inputs it embeds verbatim (`docs/asset-types/*.md`). All three
     are in `[tool.ruff] extend-exclude` because ruff 0.16+ formats Python
     inside Markdown; touching any of them outside the generator reddens the
     gate. Never run a bare `ruff format .` — CI is scoped to
     `src tests scripts`, and so is the developer guide.
   - Green the suite: `python -m pytest` + `ruff` + `mypy`.
   - Draft a conventional commit (multi-line body for multi-file changes; no
     Co-Authored-By).

6. **Act — additive (roadmap):**
   - Append an issue-ready item to `docs/roadmap.md` (one heading = one issue),
     naming the affected modules/docs from the issue's map. If a backlog batch
     now totals ~8–16h, note it as ready to graduate to an issue.

7. **Advance the committed snapshot (both paths, on the triage branch).**
   This is what moves the baseline so the next weekly run diffs against the
   accepted spec instead of re-reporting the whole accumulated backlog. Do it
   only after every additive change is harvested into the roadmap (otherwise
   unharvested additive content is lost when the baseline moves):
   - Spec drift: `cp "$SPEC" .github/upstream/openapi-v2.json`
   - SDK drift: write the new version into
     `.github/upstream/python-exoscale-version.txt`
   - Re-run `python -m pytest tests/unit/test_model_schema_drift.py` against the
     refreshed snapshot (must stay green) and commit it with the rest of the
     triage change. The baseline advances only when this PR merges — D1.

8. **Check the docs that go stale silently.** A new asset type needs more than
   its own page, and nothing in CI enforces these:
   - `docs/asset-types/README.md` — the index **table** must gain a row. Pages
     for `vpc`, `kms`, `deploy-target` and `event` all shipped in 0.6.0 without
     one, so they were unreachable by navigation.
   - Any "every asset type is live-tested" claim (README) must still be true.
     0.6.0 shipped VPC and KMS unverified (403 not-enabled / role-policy), which
     falsified it.
   - Version literals in prose (e.g. the ruff pin in the developer guide) drift
     because nothing guards them. Grep before trusting one.

9. **Wrap up — STOP at the gates.**
   - Open the PR (`gh pr create`) for the branch; comment the triage decision
     and classification on the drift issue; propose closing it if fully handled.
   - **Do not push, merge, or pull without explicit approval** (global rule).
     Merge and pull-to-clean-local stay a manual gate: present the branch/PR/
     commit and the proposed merge — then wait for the human to drive it.

## Coverage audit (run when the drift queue is quiet)

Drift triage is reactive by construction. This is the proactive half, and it is
offline work — no network, no tenant, no cost. Run it at release boundaries, or
any time an empty drift queue tempts you to report "nothing to do".

**Path-level.** Enumerate `paths` in `.github/upstream/openapi-v2.json` and
subtract what the connector actually reaches.

> ⚠️ **The trap that makes this audit wrong on the first pass.** Grepping `src/`
> for a path family **massively over-reports gaps**. The DBaaS engines are never
> spelled literally — `dbaas.py` builds
> `f"dbaas-{self._url_type(service_type)}/…"` — so `/dbaas-mysql`,
> `/dbaas-postgres`, `/dbaas-kafka` and the rest look unmodelled while being
> fully covered by the engine-generic client. The same applies to the mixins
> (`_reverse_dns.py`) and the SKS sub-resource endpoints. A first pass this way
> reported ~55 "missing" families; the real figure was a fraction of that.
> **Resolve how each path is *constructed* before calling it a gap** — read the
> client's URL construction, not just its literals. Then subtract the roadmap's
> out-of-scope list.

**Field-level.** Already tooled:

```bash
python scripts/model_schema_drift.py --summary .github/upstream/openapi-v2.json
```

Unmodelled optional fields are informational (`extra="allow"` tolerates them),
but the list mixes incidental fields with substantive ones — e.g. `Instance` has
no typed `ssh-keys`, `elastic-ips` or `private-networks`. **Curate, do not model
wholesale**; the models are a deliberate subset.

**Route findings exactly like additive drift** — roadmap backlog with an
estimate, D4 scope call for anything possibly opt-in, graduate at ~8–16h (D3).
Mark the source as the audit, not a drift issue, so the provenance stays honest.

**Worked example (2026-08-31).** The queue had been quiet since drift #71 and
the backlog stood at ~0.5h, which read as "nothing to do". A direct audit of the
committed snapshot (261 paths) found ~29–38h of never-modelled surface — the
DBaaS `database` sub-resource (the client could create users but not databases),
`/dbaas-ca-certificate`, `/sks-cluster-deprecated-resources/{id}`, DBaaS
logs/metrics, `/iam-organization-policy`, plus an engine-specific tail. Became
milestone v0.7.0 / issue #78.

## Verifying a fix to a CI gate

When a change is supposed to stop a gate from breaking, **replay the failure
rather than reasoning about it.** Copy the tracked tree to a scratch dir
(`git ls-files -z | xargs -0 cp --parents -t "$SCRATCH"`), run the offending
command there, and re-run the gate.

This is not ceremony. Excluding the generated bundle's two *output* copies from
ruff looked obviously sufficient; replaying `ruff format .` showed the sync gate
still red, because `docs/asset-types/*.md` are generator **inputs** embedded
verbatim, and reformatting an input changes what the generator would emit.
Reasoning found half the fix; replaying found the rest. For any generated
artifact, enumerate **inputs and outputs** before declaring it protected.

## Live re-verification

If a breaking change touches request payloads, flag whether a live tier run is
needed (`docs/live-test-plan.md`); credentials come from the test Infisical
project (dev env — **never** staging or prod), never hardcoded. Never let
live-tenant data into commits.

**Probe before provisioning.** Live verification of an asset type can be barred
at the tenant, and finding out by creating billable infrastructure is the
expensive way. One read-only call answers it:

- `403 "... not enabled"` on a **read-only** endpoint → the product is off for
  the whole tenant. No API key fixes this; route per D4.
- `403 "Forbidden by role policy for ..."` → an IAM gate on the key, not the
  product. The product is in scope; the key just lacks the grant.
- Catalogue endpoints are a **false green**: `GET /dbaas-service-type` lists
  ClickHouse and all its plans on a tenant that cannot touch the engine.
  Successful plan discovery proves nothing about usability.

Where a product is in scope but off for this tenant (VPC), live tests **skip**
on the 403 rather than fail.
