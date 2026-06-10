# User / Operator Guide

How to use the connector to read and manage Exoscale resources — from the
command line or from Python. For internals and how to extend it, see the
[developer guide](developer-guide.md).

## Install

```bash
pip install exoscale-connector          # or: pip install -e . from this folder
pip install "exoscale-connector[sos]"   # add Object Storage (S3) support
```

## Authentication

The connector reads credentials **from the environment only** — it never stores
them or reads them from a file:

| Variable | Required | Meaning |
|----------|----------|---------|
| `EXOSCALE_API_KEY` | yes | API key (IAM key) |
| `EXOSCALE_API_SECRET` | yes | API secret |
| `EXOSCALE_ZONE` | recommended | Default zone, e.g. `de-fra-1` |
| `EXOSCALE_API_ENDPOINT` | no | Full endpoint override (private gateway / testing) |
| `EXOSCALE_TIMEOUT` | no | Request timeout in seconds (default `60`) |
| `EXOSCALE_VERIFY_TLS` | no | `false` to disable TLS verification (not recommended) |

Inject them with your secret-management tooling rather than exporting them by
hand. The connector only reads environment variables, so any injector works
(HashiCorp Vault, Infisical, Doppler, …):

```bash
<vault-cli> run -- exoscale-security-group list
```

Use an API key scoped to only the operations you need (least privilege).

## Zones

Exoscale is region/zone-based. Each request targets one zone; set a default with
`EXOSCALE_ZONE` or pass `--zone` (CLI) / `zone=` (library). Common zones include
`ch-gva-2`, `ch-dk-2`, `de-fra-1`, `de-muc-1`, `at-vie-1`, `at-vie-2`, `bg-sof-1`.
IAM and DNS are account-global but are still reached through a zone.

## Common commands

Every asset type supports the same verbs:

```bash
exoscale-<asset> list                       # all resources in the zone
exoscale-<asset> get --id <uuid>            # one by id
exoscale-<asset> find --name <name>         # first match by name
exoscale-<asset> create --json '{...}'      # create from inline JSON
exoscale-<asset> create --file payload.json # create from a file ('-' = stdin)
exoscale-<asset> delete --id <uuid>         # delete
```

> **Secrets in payloads:** `--json` puts the payload on the command line, where it is
> visible in the process list and lands in shell history. For payloads that carry
> secrets (e.g. DBaaS passwords), prefer `--file payload.json` or `--file -` (stdin).
> Likewise, `exoscale-api-key create` prints the one-time key secret to stdout —
> avoid running it in CI steps whose output is logged.

Mutating commands wait for the asynchronous operation to finish by default; pass
`--no-wait` to return immediately. All output is JSON, so it composes with `jq`:

```bash
exoscale-security-group list | jq -r '.[].name'
```

> **CLI vs library coverage.** The CLIs cover the uniform CRUD verbs (list /
> get / find / create / delete). **Sub-resource and lifecycle operations are
> currently library-only** — examples: security-group rule
> add/delete, instance start/stop/reboot, instance-pool scale, block-volume
> attach/detach/resize, LB service add/update/delete, SKS nodepool CRUD,
> DBaaS connection-info / password-reveal, compute snapshot
> create-from-instance/export. The per-asset reference pages (see
> [asset type reference](asset-types/README.md)) show the library snippet
> for each. A future CLI refactor will expose these as subcommands.

## Library usage

```python
from exoscale_connector import ExoscaleClient
from exoscale_connector.resources.security_group import SecurityGroupClient

client = ExoscaleClient.from_env(zone="de-fra-1")
sg = SecurityGroupClient(client)

groups = sg.list()                       # List[SecurityGroup]
one = sg.get("…uuid…")                   # SecurityGroup (raises NotFoundError if absent)
maybe = sg.find_by_name("web")           # SecurityGroup | None
created = sg.create({"name": "web"})     # waits for the operation, returns the resource
sg.delete(created.id)
```

Error handling:

```python
from exoscale_connector import NotFoundError, APIError, OperationError

try:
    sg.get("does-not-exist")
except NotFoundError:
    ...                # 404
except APIError as e:
    print(e.status_code, e.payload)
except OperationError as e:
    print("async op failed:", e.state, e.payload)
```

## Asset type coverage

| Domain | Asset type | CLI |
|--------|-----------|-----|
| Network | Security group (+ rules) | `exoscale-security-group` |
| Network | Elastic IP | `exoscale-elastic-ip` |
| Network | Private network | `exoscale-private-network` |
| Network | Load balancer (+ services) | `exoscale-load-balancer` |
| Compute | Instance (+ start/stop/reboot) | `exoscale-instance` |
| Compute | Instance pool (+ scale) | `exoscale-instance-pool` |
| Compute | Anti-affinity group | `exoscale-anti-affinity-group` |
| Compute | Snapshot | `exoscale-snapshot` |
| Storage | Block volume (+ attach/detach/resize) | `exoscale-block-volume` |
| Storage | Block volume snapshot | `exoscale-block-volume-snapshot` |
| Storage | Object Storage bucket (S3) | `exoscale-bucket` |
| IAM | API key | `exoscale-api-key` |
| IAM | Role | `exoscale-iam-role` |
| IAM | User / org member | `exoscale-iam-user` |
| IAM | SSH key | `exoscale-ssh-key` |
| Managed | DNS domain + records | `exoscale-dns` |
| Managed | DBaaS service | `exoscale-dbaas` |
| Managed | SKS cluster (+ nodepools) | `exoscale-sks` |

The behaviour above (verbs, auth, zones, output) is identical across every type.
The `dns`, `dbaas`, `sks`, `load-balancer` and `security-group` clients add a few
type-specific commands for their sub-resources (records, nodepools, services,
rules) and lifecycle actions; run `exoscale-<type> --help` for the full list.

> **Object Storage note:** buckets are S3-compatible, not part of the APIv2.
> `exoscale-bucket` uses `boto3` (the `[sos]` extra) and the SOS endpoint, but
> reuses the same `EXOSCALE_API_KEY` / `EXOSCALE_API_SECRET` credentials.

## Per-asset reference

For each asset type's fields, gotchas, library snippets, and a complete
end-to-end example, see the
**[asset type reference](asset-types/README.md)**. Every page is backed by a
passing live test (see [live-test-results.md](live-test-results.md)).

For building IAM role policies (the one area with real depth), see the
**[IAM policy cookbook](iam-policy-cookbook.md)** — helper constructors plus
copy-paste recipes for the common cases.
