---
name: exoscale-drift-triage
description: >-
  Use to triage upstream-drift issues in the exoscale-connector repo — the
  weekly upstream-drift workflow files them when the APIv2 OpenAPI spec or the
  official exoscale SDK changes. Walks: find the open issue, read its prepared
  analysis, classify each change as breaking-fix-now or additive-roadmap, then
  produce a branch + PR (breaking) or roadmap entry (additive), comment the
  decision, and stop at the human gate before merge/push/pull.
---

# exoscale-connector drift triage

The `upstream-drift` workflow (`.github/workflows/upstream-drift.yml`) runs
Mondays and files/updates a single open issue per source, labelled
`upstream-drift`, with one of these titles:

- `Upstream drift: APIv2 OpenAPI spec changed`
- `Upstream drift: new official exoscale SDK release on PyPI`

The issue body already contains the analysis: an evaluation checklist, an
**Affected connector modules** map, a **Model ↔ spec field drift** table, and
the oasdiff changelog. Do not re-derive these — read them, then decide and act.

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

## Procedure

1. **Find work.**
   `gh issue list --label upstream-drift --state open`.
   None → report "no open drift" and stop.

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
   - Re-read the gotchas on each affected `docs/asset-types/*.md` page; a spec
     change can invalidate a documented gotcha.

4. **Classify each change** per D3:
   - **Breaking** (red CI: rename/removal/retype/newly-required request field,
     or an invalidated gotcha) → fix now.
   - **Additive** (new optional fields, tolerated by `extra="allow"`; new
     endpoints/asset types not yet modelled) → roadmap.

5. **Act — breaking (fix now):**
   - Branch: `git switch -c fix/drift-<short-topic>`.
   - Reconcile the model/docs; or, if the divergence is intentional and
     live-verified, record it in `ALLOWED_DIVERGENCES` (model drift) /
     `MODULE_SIBLING_OPERATIONS` (operations) with a reason.
   - Regenerate AI artifacts: `python scripts/generate_llms_txt.py`
     (then `--check` must pass — keeps llms.txt + both skill copies in sync).
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

8. **Wrap up — STOP at the gates.**
   - Open the PR (`gh pr create`) for the branch; comment the triage decision
     and classification on the drift issue; propose closing it if fully handled.
   - **Do not push, merge, or pull without explicit approval** (global rule).
     Merge and pull-to-clean-local stay a manual gate: present the branch/PR/
     commit and the proposed merge — then wait for the human to drive it.

## Live re-verification

If a breaking change touches request payloads, flag whether a live tier run is
needed (`docs/live-test-plan.md`); credentials come from the test Infisical
project (dev env), never hardcoded. Never let live-tenant data into commits.
