# Asset type reference

One page per asset type the connector supports. Every page has the same six
sections — **Overview**, **Model**, **CLI**, **Library**, **Gotchas**,
**End-to-end example** — and is backed by a passing
[live test](../live-test-plan.md).

If something on a page contradicts the live behaviour, the live test is the
source of truth — open an issue and the page will be corrected.

## Capability matrix

| Asset type | CLI binary | Live-tested | Tier |
|---|---|---|---|
| [security-group (+rules)](security-group.md) | `exoscale-security-group` | ✅ | 1 |
| [private-network](private-network.md) | `exoscale-private-network` | ✅ | 1 |
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
| [snapshot (compute)](snapshot.md) | `exoscale-snapshot` | ✅ create/list/get/export/delete | 3 |
| [load-balancer (+services)](load-balancer.md) | `exoscale-load-balancer` | ✅ | 4 |
| [dbaas](dbaas.md) | `exoscale-dbaas` | ✅ (users/update: pending) | 4 |
| [sks (cluster + nodepool)](sks.md) | `exoscale-sks` | ✅ | 4 |
| [zone](zone.md) | `exoscale-zone` | pending (smoke test added) | 0 |
| [template](template.md) | `exoscale-template` | pending (smoke test added) | 0 |
| [instance-type](instance-type.md) | `exoscale-instance-type` | pending (smoke test added) | 0 |

New surfaces from the extensions branch (instance scale, reverse DNS, SOS
objects, DBaaS users/update, `ensure()`) ship with live tests wired into their
tiers but are marked **pending** until the next recorded live run.

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
  success, 1 on API/connector error, 2 on argparse error.
- **All resources** are pydantic v2 models with snake_case attributes that
  auto-map to the API's kebab-case JSON keys (e.g. `flow_direction` ↔
  `flow-direction`). Unknown server fields pass through (`extra="allow"`),
  so the connector keeps working when the API adds fields ahead of the model.
- **Async operations** are awaited by default — pass `wait=False` to return
  the operation object without polling.
