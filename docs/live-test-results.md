# Live test results

Per-run log of the live-test tiers run against a real Exoscale account, with
exact dates, what was exercised, what passed, and what didn't.

## Tier 1 — 2026-06-01 (zone `at-vie-1`)

**Context:** test/staging tenant, credentials injected via the operator's
secret-management tooling; machine-identity auth (no secrets on the CLI).

**Flags:** `EXOSCALE_RUN_LIVE_TESTS=1 EXOSCALE_TEST_TIER_1=1 EXOSCALE_ALLOW_MUTATION=1 EXOSCALE_TEST_ZONE=at-vie-1`

**Outcome: 6 passed · 26.8 s total · 0 leaked resources** (tracker confirmed empty on teardown).

| # | Asset type | API operations exercised | Result |
|---|-----------|--------------------------|--------|
| 1 | `security-group` | `create` → `get` → `find_by_name` → `add_rule` (ingress tcp/443) → `get` (assert rule present) → `delete_rule` → `get` (assert rule gone) → `delete` | ✅ pass |
| 2 | `private-network` | `create` → `get` → `find_by_name` → `update` (description) → `get` (assert updated) → `delete` | ✅ pass |
| 3 | `anti-affinity-group` | `create` → `get` → `find_by_name` → `delete` | ✅ pass |
| 4 | `ssh-key` | `create` (ephemeral ed25519, OpenSSH-encoded public key) → `get` (assert fingerprint present) → `delete` | ✅ pass (after fix — see below) |
| 5 | `iam-role` | `create` (deny-all policy) → `get` → `update` (description) → `get` (assert updated) → `delete` | ✅ pass |
| 6 | `dns` | `create_domain` → `get_domain` → `create_record` (A) → `list_records` (assert present) → `update_record` (TTL) → `get_record` (assert updated) → `delete_record` → `delete_domain` | ✅ pass (after fix — see below) |

### Bugs found and fixed in this run

1. **ssh-key — `create()` returned an empty model.**
   The Exoscale APIv2 `POST /ssh-key` answers with an async-operation envelope
   (`{"id": <op-uuid>, "state": "success"}`) that has **no `reference` field** —
   for name-keyed resources, the resource id *is* the name we just submitted.
   The base `ResourceClient.create()` fell back to `model_validate(response)`
   and returned an SSHKey with all fields `None`.

   **Fix** (`src/exoscale_connector/resources/_base.py`): when
   `id_field == "name"`, the base `create()` now passes the payload's `name`
   as the `fallback_id` to `_resolve_mutation`, which re-fetches via
   `GET /<collection>/<name>`. Covered by a new unit regression test
   (`tests/unit/test_ssh_key.py::test_create_operation_without_reference_refetches_by_name`).

2. **dns — `list_records` used the wrong wrapper key.**
   An early version of `dns.py` used `dns-records` as the JSON wrapper key
   for `GET /dns-domain/{id}/record`; the live API actually returns
   `dns-domain-records`. As a result, `list_records` always returned an empty
   list against the real API, even though every record was created correctly.

   **Fix** (`src/exoscale_connector/resources/dns.py`): `list_records` now
   reads `dns-domain-records` (matching the live API). An earlier iteration
   kept a silent fallback to `dns-records` for forward compatibility, but
   that was later removed — a silent fallback would mask a future
   wrapper-key change instead of letting the live test fail loudly.

### What didn't get exercised at first

- **api-key** — covered in a follow-up run (see below) after the test was
  added; the gate `EXOSCALE_TEST_TIER_1_API_KEY=1` keeps it off by default
  so casual Tier 1 runs don't produce a secret-bearing response.

### Follow-up: api-key — 2026-06-01 (zone `at-vie-1`)

**Flags:** `EXOSCALE_RUN_LIVE_TESTS=1 EXOSCALE_TEST_TIER_1=1 EXOSCALE_TEST_TIER_1_API_KEY=1 EXOSCALE_ALLOW_MUTATION=1`

**Outcome: 1 passed in 0.6 s · 0 leaked resources.**

| Asset type | API operations exercised | Result |
|---|---|---|
| `api-key` (and a temp `iam-role` to bind it) | create role (deny-all) → create key bound to role → assert `secret` returned (never printed) → list (assert secret no longer returned) → delete key → delete role | ✅ pass |

### Safety check

- Every created resource carried the `conn-test-<runid>-` prefix.
- The tracker's session-end sweep ran on every test and reported zero leaks.
- No existing resource in the tenant was touched.

---

## Tier 2 — 2026-06-01 (zone `at-vie-1`)

**Context:** same test tenant, machine-identity-authenticated secret injection.

**Flags:** `EXOSCALE_RUN_LIVE_TESTS=1 EXOSCALE_TEST_TIER_2=1 EXOSCALE_ALLOW_MUTATION=1 EXOSCALE_TEST_ZONE=at-vie-1`

**Outcome: 3 passed · 17.8 s total · 0 leaked resources.**

| # | Asset type | API operations exercised | Result |
|---|-----------|--------------------------|--------|
| 1 | `elastic-ip` | `create` (inet4) → `get` (assert IP assigned) → `update` (description) → `get` (assert updated) → `delete` | ✅ pass |
| 2 | `bucket` (Object Storage, S3 via boto3) | `create` (globally unique name) → `exists` → `list` (assert present) → `delete` → `exists` (assert false) | ✅ pass |
| 3 | `block-volume` + `block-volume-snapshot` | `create` (10 GiB) → `get` (assert size/state=detached) → `find_by_name` → `create_snapshot` (operation → reference) → `get` (snapshot) → `delete_snapshot` → `delete_volume` | ✅ pass |

### Bugs found and fixed in this run

1. **block-volume `list_key` was wrong.** The connector originally used
   `"block-storages"`; the live API returns `"block-storage-volumes"`. Same
   class of mistake as the DNS `list_records` wrapper-key bug. Fix in
   `resources/block_volume.py`; unit tests updated.
2. **block-volume `resize` endpoint shape (partial fix — see Tier 3 #4).** The
   connector was using `PUT /block-storage/{id}/resize` (slash form); the API
   rejects that as a malformed UUID. As an initial fix the connector was
   switched to `PUT /block-storage/{id}` with `{"size": <n>}` in the body.
   **That turned out to be wrong** — the plain PUT silently drops the size
   field. The real endpoint is `PUT /block-storage/{id}:resize-volume` with
   size in **bytes** (not GiB), as Tier 3 ultimately proved. See Tier 3
   bug #4 below for the corrected fix.
   The `attach` / `detach` colon-action paths were updated in the same
   change and confirmed correct by the Tier 3 online run.
3. **`resize` is online-only.** Even with the correct endpoint, `PUT` returns
   `state: success` but the size never actually changes unless the volume is
   attached to a running instance. Resize / attach / detach therefore moved
   from Tier 2 to Tier 3 where an instance fixture is available; Tier 2
   block-volume now covers only detached operations (create / get / find /
   snapshot / delete).

### What didn't get exercised (intentionally)

- `block-volume.attach`, `block-volume.detach`, `block-volume.resize` — moved
  to Tier 3 (need a running instance to test).
- The connector's `BlockVolume.snapshots` field was originally mapped to
  the wrong wrapper key (auto-generated kebab alias `snapshots` vs. the
  live API's `block-storage-snapshots`), so the typed list was always
  `None` even when the volume had snapshots. **Fixed** with an explicit
  `Field(alias="block-storage-snapshots")` on the model field; a unit
  regression test locks it in.

---

## Tier 3 — 2026-06-01 (zone `at-vie-1`)

**Context:** same test tenant, machine-identity-authenticated secret injection.

**Flags:** `EXOSCALE_RUN_LIVE_TESTS=1 EXOSCALE_TEST_TIER_3=1 EXOSCALE_ALLOW_MUTATION=1 EXOSCALE_TEST_ZONE=at-vie-1`

**Outcome: 3 passed · 1 skipped (tenant quota) · 9 min 51 s · 0 leaked resources.**

| # | Asset type | API operations exercised | Result |
|---|-----------|--------------------------|--------|
| 1 | `instance` | `create` (standard.tiny, 10 GiB) → `get` → `find_by_name` → `update` (labels) → `stop` → `start` → `reboot` → `delete` | ✅ pass |
| 2 | `instance-pool` | `create` (size=1) → `get` → `scale` to 2 → wait `running` → `scale` to 1 → wait `running` → `delete` | ✅ pass |
| 3 | `snapshot` (compute) | `create_from_instance` → poll until `state == "exported"` → `list` (assert present) → `delete` | ✅ pass |
| 4 | `block-volume` online (attach/resize/detach) | `attach` (standard.small required) → wait `attached` → `resize` → ⚠️ skipped on tenant block-storage quota | ⚠️ skip |

### Bugs found and fixed in this run

1. **instance.start / stop / reboot used POST; the API requires PUT.**
   The connector originally issued `POST instance/{id}:start` but the live API
   returns 404 on POST and accepts PUT. Fix in `resources/instance.py`; unit
   tests updated.
2. **compute snapshot terminal state is `"exported"`, not `"ready"`.**
   The test was waiting for `"ready"` and timed out at 15 minutes. Current
   Exoscale auto-exports snapshots; the documented terminal state is
   `"exported"`. Test now accepts either, future-proofed.
3. **block-storage attach requires at least `standard.small`.**
   `standard.tiny` is rejected with 409 *Instance size must be at least small*.
   The block-volume online test now provisions a `standard.small` instance.
4. **block-volume resize endpoint is `:resize-volume`, not `/resize` nor
   plain `PUT`.** The connector originally used `/resize` (404). Plain
   `PUT /block-storage/{id}` accepts the size field on the wire but silently
   drops it. The actual endpoint is `PUT /block-storage/{id}:resize-volume`,
   confirmed against the OpenAPI spec.
5. **block-volume resize `size` is in BYTES, not GiB** — despite the OpenAPI
   spec documenting GiB. Empirically verified: a request with `size = 11`
   returns `400 bad request` (interpreted as 11 bytes, below the current 10
   GiB volume size); a request with `size = 11 * 1024**3` returns
   `409 quota exceeded` (interpreted as ~11 GiB and the tenant quota
   bites). The connector now converts caller-side GiB to bytes on the wire
   so external callers keep using the same unit as `create` and `get`.
6. **Cleanup ordering when a mid-test failure left a volume attached.** The
   tracker swept in reverse-creation order (volume, then instance), but a
   delete-volume request fails with 412 while the volume is still attached
   — and by the time the next sweep step deleted the instance, the volume
   was orphaned (the API auto-detaches it from a deleted instance, but the
   tracker had already moved on). The volume teardown now detaches first
   if still attached.

### What didn't get exercised (intentionally)

- **`block-volume.resize` size-change assertion** — the tenant's
  block-storage quota is ~10 GiB total, so any resize from 10 GiB exceeds
  the quota. The test self-skips on the 409. To actually verify the
  size-change end-to-end, run against a tenant with more block-storage
  quota and the test will assert size==20 after the resize call.

### Follow-up: snapshot `export` — 2026-06-02 (zone `at-vie-1`)

**Context:** the compute-snapshot test was extended to exercise
`SnapshotClient.export()` (previously mocked-only). First run failed; re-run
after the fix passed (2 min 1 s, 0 leaked resources).

**Bug found and fixed:**

7. **compute snapshot `export` endpoint is `:export`, not `/export`.** The
   connector posted to `/snapshot/{id}/export` (slash) and the live API
   returned `404 not found`; the actual action endpoint is
   `POST /snapshot/{id}:export` (colon), consistent with every other APIv2
   action and confirmed against the OpenAPI spec. The mocked unit test had
   baked in the same wrong path, so it never caught it — the same blind spot
   pattern as the earlier wrapper-key / HTTP-method bugs. Fixed in
   `resources/snapshot.py`; unit mocks corrected. The test now also asserts a
   non-empty presigned URL is returned (never printed).

---

## Tier 4 — 2026-06-01 (zone `at-vie-1`)

**Context:** same test tenant, machine-identity-authenticated secret injection.

**Flags:** `EXOSCALE_RUN_LIVE_TESTS=1 EXOSCALE_TEST_TIER_4_LB=1 EXOSCALE_TEST_TIER_4_DBAAS=1 EXOSCALE_TEST_TIER_4_SKS=1 EXOSCALE_ALLOW_MUTATION=1 EXOSCALE_TEST_ZONE=at-vie-1`

**Outcome: 3 passed across multiple iterations · 0 leaked resources at end** (two DBaaS orphans appeared on early v1/v2 attempts and were cleaned up manually; the connector + test were then hardened to prevent future leaks — see fixes below).

| # | Asset type | API operations exercised | Result |
|---|-----------|--------------------------|--------|
| 1 | `load-balancer` (+ service) | Create backing instance-pool → create LB → wait `running` → `add_service` (TCP/80 → pool, tcp healthcheck) → `get` (assert service present) → `update_service` (full-spec replace, new healthcheck interval) → `delete_service` → `delete` LB → delete pool | ✅ pass |
| 2 | `dbaas` (Postgres, cheapest plan) | `list_service_types` → pick cheapest pg plan → `create` (POST `dbaas-postgres/<name>`, body `{"plan": ...}`) → wait `running` (~2 min on hobbyist-2) → `get` (overridden two-step lookup) → `get_connection_info` (assert uri-params + connection-info present, never printed) → `reveal_user_password` (assert password non-empty, never printed) → `delete` | ✅ pass |
| 3 | `sks` (cluster + nodepool + kubeconfig) | `resolve_sks_version` → `create` cluster (`level: starter`, calico CNI, smallest version) → wait `running` (~10 min) → `generate_kubeconfig` (with `user` + `groups`, asserted present never printed) → `create_nodepool` (size=1, standard.small) → wait nodepool `running` → `update_nodepool` size 1→2 → wait → scale back 2→1 → `delete_nodepool` → `delete` cluster | ✅ pass |

### Bugs found and fixed in this tier

1. **SKS cluster create field is `level`, not `service-level`.**
   The connector originally used `service-level`; the live API rejects it
   with `400: missing keys 'level'`. Test payload fixed.
2. **SKS `generate_kubeconfig` requires `groups`, not just `user`.**
   `400: missing keys 'groups'`. The test now passes
   `groups=["system:masters"]`; the connector docstring is updated to
   document both required fields.
3. **DBaaS short/long type-name mismatch (`pg` ↔ `postgres`).** The Exoscale
   API uses *short* names in `list_service_types` (returns `{"name": "pg"}`)
   but *long* names in URL paths (`POST /dbaas-postgres/...`). The connector
   now keeps a one-entry alias map (`pg → postgres`) and translates at the
   URL boundary; callers can pass either form.
4. **DBaaS `GET /dbaas-service/<name>` is list-only.** The generic
   collection path returns 404 on individual GETs — that endpoint is
   *only* a list. The connector now overrides `get()` to do a two-step
   lookup: list to discover the service's type, then fetch the detail body
   via the type-specific `dbaas-{long-type}/<name>` path.
5. **DBaaS `connection-info.uri` is a LIST, not a string.** Postgres returns
   multiple endpoint URIs (primary + replicas). `DBaaSConnectionInfo.uri`
   model field changed from `Optional[str]` to `Optional[List[str]]`.
6. **LB `update_service` is a full-resource replace, not a partial PATCH.**
   Sending only `{"healthcheck": {...}}` was rejected with `400` because
   missing required fields like `protocol` get defaulted to garbage
   (literally `"HTTP/1.1"` parsed from the request line). Test now
   resends the full service spec on update.
7. **Tracker registration timing.** When DBaaS `create()` raised partway
   through (POST succeeded, re-fetch failed), `tracker.register()` was
   never reached — leaking the actual server-side service. The Tier 4
   tests now register cleanup **before** calling `create()`, so any
   partial-create leak still gets swept.

## Extensions validation run — 2026-06-10 (zone `at-vie-1`)

**Context:** full ladder re-run (smoke → tier 4) validating the
`fix/assessment-findings` + `feat/connector-extensions` branches, focused on
the endpoints implemented from the API reference without live evidence
("pending live verification"). All tiers ran with `EXOSCALE_RECORD=1`;
the reviewed recordings now seed `tests/recorded/` and replay in CI.
Credentials injected via the operator's vault tooling (machine-identity
auth, no secrets on the CLI or in the transcript).

**Outcome: all tiers green · 0 leaked resources after every run** (per-run
tracker sweeps plus a final read-only tenant-wide scan for `conn-test-*`).

| Tier | Flags (beyond master switches) | Result | Runtime |
|------|-------------------------------|--------|---------|
| 0 smoke | — | 21 passed (incl. 3 new catalogue tests: zones, templates, instance-types) | 6 s |
| 1 | `EXOSCALE_TEST_TIER_1=1` | 7 passed, 1 skipped (api-key gate off) — after 1 fix, see below | 26 s |
| 2 | `EXOSCALE_TEST_TIER_2=1` | 5 passed — after 2 fixes, see below | 19 s |
| 3 | `EXOSCALE_TEST_TIER_3=1` | 4 passed, 1 skipped (volume-resize quota self-skip) | 11:26 |
| 4 | `EXOSCALE_TEST_TIER_4_LB/DBAAS/SKS=1` | 3 passed | 22:30 |

Tier 3 was run twice (the first run predated the recorder fix below, so it
recorded nothing). The re-run hit an `OperationTimeoutError` on a plain
instance **stop** — the operation did not settle within the 600 s
`operation_timeout` (the zone was visibly slow that evening; the same run
took 21 min vs 11 min earlier). A scale-only retry passed in 60 s once the
zone recovered: infrastructure flake, not a connector bug — and evidence the
operation-timeout guard works.

### Bugs found and fixed in this run

1. **iam-role — there is no `:assume-role-policy` sub-endpoint.**
   `PUT /iam-role/{id}:assume-role-policy` returns **404**. The live API
   takes `assume-role-policy` in the body of the generic
   `PUT /iam-role/{id}` instead (confirmed against the published OpenAPI
   spec: only `:policy` has a dedicated sub-endpoint).
   **Fix** (`resources/iam_role.py`): `set_assume_role_policy()` now routes
   through the generic update; signature and `Operation` return unchanged.

2. **reverse-dns — set is a POST, not a PUT.**
   `PUT /reverse-dns/{kind}/{id}` returns **404**; create/update of the PTR
   record is **POST**. **Fix** (`resources/_reverse_dns.py`), applies to
   both the elastic-ip and instance variants through the shared mixin;
   live-exercised on elastic-ip (`test_elastic_ip_reverse_dns`).

3. **SOS — unconfigured bucket lifecycle answers 200, not an error.**
   AWS S3 raises `NoSuchLifecycleConfiguration`; Exoscale SOS returns 200
   with no rules. **Fix** (`resources/object_storage.py`):
   `get_lifecycle()` normalises both shapes to `None`.

### Test-infrastructure fixes from this run

4. **The extended-timeout tier-3/4 client recorded nothing.**
   `tier_3_client` builds a fresh `ExoscaleClient`, so the wire recorder
   attached to `live_client`'s session never saw tier 3/4 traffic. The
   fixture now attaches its own recorder.

5. **Recordings leaked PII from the shared tenant.** Real user emails
   (inside security-group descriptions and IAM user lists) and Exoscale API
   key ids (`EXO…`, the public half of a credential pair) survived
   key-based redaction. The recorder now scrubs both patterns from every
   string value; committed recordings were re-scrubbed and verified clean.

6. **`release.yml` — publish action pinned to a commit SHA** (it receives
   the OIDC token for PyPI trusted publishing; flagged by security review).

### Verification status after this run

| Surface | Status |
|---|---|
| zones / templates / instance-types catalogues | ✅ live-verified (smoke) |
| `ensure()` idempotency | ✅ live-verified (tier 1) |
| SOS object put/list/get/presign/delete + lifecycle/CORS read | ✅ live-verified (tier 2) |
| Elastic IP reverse DNS | ✅ live-verified (tier 2) |
| Instance reverse DNS | shared mixin verified via elastic-ip; instance-specific calls not exercised |
| Instance vertical scaling (`:scale`) | ✅ live-verified (tier 3) |
| DBaaS `update`, `create_user`, `delete_user` | ✅ live-verified (tier 4) |
| DBaaS `reset_user_password` | not exercised (would disrupt `avnadmin` mid-test) |
| Template `register` / `delete` | still pending — needs a hosted disk image; deliberately out of scope (see template.md gotcha) |

**Cost:** well under €0.15 for the whole run (two tier-3 passes + retry +
full tier 4).
