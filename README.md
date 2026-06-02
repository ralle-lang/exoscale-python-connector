# exoscale-connector

A clean, typed, reusable Python connector for the **Exoscale APIv2**. It talks to
the HTTP API directly — **no `exo` CLI and no Ansible required** — so it can be
dropped into any project that needs to read or manage Exoscale resources
programmatically.

- **Typed** — every request/response is a [pydantic](https://docs.pydantic.dev) v2
  model, so you get validation and editor autocompletion.
- **One module per asset type** — `security-group`, `instance`, `elastic-ip`,
  `dns`, `dbaas`, `sks`, … each with a small, uniform client.
- **Library + CLI** — import it, or use the per-asset command-line tools.
- **Self-contained** — runtime deps are just `requests` + `pydantic`; copy the
  package into another repo and it keeps working.
- **Secret-safe** — credentials come only from the environment; nothing is
  hardcoded or read from disk.

## Install

```bash
pip install -e ".[dev]"          # from this folder, for development
# or, once published / vendored:
pip install exoscale-connector
```

Object Storage (S3-compatible) support pulls in `boto3`:

```bash
pip install "exoscale-connector[sos]"
```

## Quickstart (library)

```python
from exoscale_connector import ExoscaleClient
from exoscale_connector.resources.security_group import (
    SecurityGroupClient, SecurityGroupRule,
)

# Credentials from EXOSCALE_API_KEY / EXOSCALE_API_SECRET in the environment.
client = ExoscaleClient.from_env(zone="de-fra-1")
sg = SecurityGroupClient(client)

for group in sg.list():
    print(group.id, group.name)

group = sg.create({"name": "web", "description": "public web tier"})
sg.add_rule(group.id, SecurityGroupRule(
    flow_direction="ingress", protocol="tcp",
    start_port=443, end_port=443, network="0.0.0.0/0",
))
```

## Quickstart (CLI)

```bash
export EXOSCALE_API_KEY=... EXOSCALE_API_SECRET=... EXOSCALE_ZONE=de-fra-1

exoscale-security-group list
exoscale-security-group get --id <uuid>
exoscale-security-group create --json '{"name": "web"}'
exoscale-security-group delete --id <uuid>
```

> In practice, inject the credentials with your secret-management tooling rather
> than exporting them by hand. The connector only reads environment variables, so
> any injector works (HashiCorp Vault, Infisical, Doppler, …), e.g.
> `<vault-cli> run -- exoscale-security-group list`.

## Documentation

- **[User / operator guide](docs/user-guide.md)** — installing, authenticating,
  zones, and the common commands shared by every asset type.
- **[Asset type reference](docs/asset-types/README.md)** — one page per asset
  type with model schema, CLI subcommands, library snippets, gotchas, and a
  runnable end-to-end example backed by a passing live test.
- **[IAM policy cookbook](docs/iam-policy-cookbook.md)** — helper constructors
  and copy-paste recipes for IAM role policies (the one area with real depth).
- **[Developer guide](docs/developer-guide.md)** — architecture, how to add a
  new asset type, and the testing strategy.
- **[Live test plan](docs/live-test-plan.md)** — tiered per-asset live-test
  design (safety rails, naming prefix, cleanup invariants, cost model).
- **[Live test results](docs/live-test-results.md)** — run log of every live
  test executed against a real Exoscale tenant, plus the bugs each tier
  surfaced and how they were fixed.

Every asset type the connector supports has a live test that has actually run
end-to-end against a real account; the gotchas in the asset-type pages are
empirical, not theoretical.

## Maintenance & support

This is a personal project, maintained on a **best-effort, occasional basis** —
not full-time and not on a fixed schedule. It's shared because it may be useful
to others, not as a supported product. Issues and pull requests are welcome and
will be looked at when time allows, but there is **no guaranteed response time or
release cadence**. The API surface it tracks can drift; if you depend on it,
pin a version and don't hesitate to fork and adapt it — that's encouraged.

## License

Released under the [MIT License](LICENSE) — free to use, modify, and
redistribute, including commercially. Provided **as-is, without warranty of any
kind**; use entirely at your own risk. The only condition is that the copyright
and permission notice are kept in copies.
