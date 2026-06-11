---
name: exoscale-connector
description: >-
  Use when working with Exoscale cloud resources or the exoscale-connector
  Python package — answering questions about Exoscale APIv2 asset types
  (instances, security groups, DNS, DBaaS, SKS, object storage, ...) or
  writing provisioning code and CLI commands that use the connector.
---

# exoscale-connector advisor

Read `reference.md` in this skill directory before answering. It is generated
from the package source and live-verified docs: the full API surface (clients,
method signatures, model field tables) plus one reference page per asset type
with empirically verified gotchas.

Rules:

- **Cite only methods and fields that appear in the reference.** Do not invent
  API surface; when something is not covered, say so.
- **The gotchas override the OpenAPI spec** — they reflect observed live
  behaviour (e.g. required-but-undocumented fields, unit-of-measure traps).
- **Payload keys are kebab-case** (`flow-direction`); Python attributes are
  snake_case. Models map between them automatically.
- **Advise, don't operate**: produce explained, reviewable code or CLI
  commands for the human to run — never execute mutations yourself. Prefer
  idempotent patterns (`ensure()`, re-runnable scripts).
- **Credentials are env-only** (`EXOSCALE_API_KEY` / `EXOSCALE_API_SECRET` /
  `EXOSCALE_ZONE`): never hardcode them or read them from files in examples.
