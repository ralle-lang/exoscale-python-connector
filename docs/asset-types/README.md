# Asset type reference

One page per asset type the connector supports. Every page follows the same
layout: an overview paragraph, then **Model**, **CLI**, **Library**,
**Gotchas** and **End-to-end example** (read-only catalogues such as zone or
instance-type skip the example). The matrix below says how far each type is
backed by the [live tests](../live-test-plan.md).

If something on a page contradicts the live behaviour, the live test is the
source of truth — open an issue and the page will be corrected.

## Capability matrix

| Asset type | CLI binary | Live-tested | Tier |
|---|---|---|---|
| [security-group (+rules)](security-group.md) | `exoscale-security-group` | ✅ | 1 |
| [private-network](private-network.md) | `exoscale-private-network` | ✅ CRUD (2026-06-01); attach/detach, `update_instance_ip` and `reset_field` not live-verified (create answers 403 "not enabled" on the test tenant since 2026-11-09) | 1/3 |
| [anti-affinity-group](anti-affinity-group.md) | `exoscale-anti-affinity-group` | ✅ | 1 |
| [ssh-key](ssh-key.md) | `exoscale-ssh-key` | ✅ | 1 |
| [iam-role](iam-role.md) | `exoscale-iam-role` | ✅ | 1 |
| [iam-user](iam-user.md) | `exoscale-iam-user` | read-only | — |
| [api-key](api-key.md) | `exoscale-api-key` | ✅ (gated) | 1 (opt-in, `EXOSCALE_TEST_TIER_1_API_KEY=1`) |
| [dns (domain + records)](dns.md) | `exoscale-dns` | ✅ | 1 |
| [elastic-ip](elastic-ip.md) | `exoscale-elastic-ip` | ✅ | 2 |
| [object-storage bucket](object-storage.md) | `exoscale-bucket` | ✅ | 2 |
| [block-volume](block-volume.md) | `exoscale-block-volume` | ✅ create/snapshot/delete (Tier 2); attach/detach (Tier 3); resize endpoint+method verified, size-change assertion self-skips on tenant quota | 2/3 |
| [block-volume-snapshot](block-volume-snapshot.md) | `exoscale-block-volume-snapshot` | ✅ | 2 |
| [instance (+lifecycle)](instance.md) | `exoscale-instance` | ✅ | 3 |
| [instance-pool (+scale)](instance-pool.md) | `exoscale-instance-pool` | ✅ | 3 |
| [snapshot (compute)](snapshot.md) | `exoscale-snapshot` | ✅ create/list/get/export/revert/promote/delete | 3 |
| [load-balancer (+services)](load-balancer.md) | `exoscale-load-balancer` | ✅ | 4 |
| [dbaas](dbaas.md) | `exoscale-dbaas` | ✅ | 4 |
| [sks (cluster + nodepool)](sks.md) | `exoscale-sks` | ✅ | 4 |
| [zone](zone.md) | `exoscale-zone` | ✅ read-only (list) | 0 |
| [template](template.md) | `exoscale-template` | ✅ list/find (0), register/delete (1), copy (3) | 0/1/3 |
| [instance-type](instance-type.md) | `exoscale-instance-type` | ✅ read-only (list/find-slug) | 0 |
| [deploy-target](deploy-target.md) | `exoscale-deploy-target` | ✅ read-only (list/get) | 0 |
| [event](event.md) | `exoscale-event` | ✅ read-only (list) | 0 |
| [vpc (+subnets, routes)](vpc.md) | `exoscale-vpc` | ✅ all endpoints (2026-11-02); subnet `ipv4` pin 2026-11-09 | 1/3 |
| [kms (key + crypto)](kms.md) | `exoscale-kms` | ✅ all endpoints (2026-11-02) | KMS opt-in |

Instance scale, elastic-IP reverse DNS, SOS objects, DBaaS users/update, and
`ensure()` were all live-verified in the 2026-06-10 extensions validation run (see
[live-test-results.md](../live-test-results.md)). Three spec-vs-reality
divergences were found and fixed during that run.

## Page template

```
# <asset-type>
Overview — one paragraph.
## Model
Field table from the pydantic model.
## CLI
Every subcommand with a copy-pasteable example invocation.
## Library
Python snippet for each operation.
## Gotchas
Caveats verified by the live test (e.g. unit-of-measure quirks,
required-but-undocumented fields, quota constraints).
## End-to-end example
The full lifecycle distilled from the corresponding live test.
```

## Conventions used on every page

- **Authentication** is always env-based: `EXOSCALE_API_KEY` /
  `EXOSCALE_API_SECRET` / `EXOSCALE_ZONE`. Inject with your secret manager
  (HashiCorp Vault, Infisical, Doppler, …); the connector reads only env vars.
- **JSON output** from CLIs goes to stdout; errors to stderr; exit 0 on
  success, 1 on API/connector error, 2 on argparse error, 130 on Ctrl-C.
- **All resources** are pydantic v2 models with snake_case attributes that
  auto-map to the API's kebab-case JSON keys (e.g. `flow_direction` ↔
  `flow-direction`). Unknown server fields pass through (`extra="allow"`),
  so the connector keeps working when the API adds fields ahead of the model.
- **Async operations** are awaited by default — pass `wait=False` to return
  the operation object without polling.
