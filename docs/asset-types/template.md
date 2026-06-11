# template

Compute templates — the boot images instances are created from. List Exoscale's
stock images (`visibility="public"`, the API default) or your own registered
ones (`"private"`). Registering is a normal `create` with a source URL +
checksum.

## Model

| Field | Type | Notes |
|---|---|---|
| `id` | str (uuid) | |
| `name` / `description` | str | |
| `family` | str | OS family, e.g. `Linux Ubuntu` — what `find_linux` matches on |
| `version` / `build` | str | |
| `size` | int | minimum disk the template needs, **bytes** |
| `visibility` | str | `public` \| `private` |
| `url` / `checksum` | str | registration source (private templates) |
| `boot_mode` | str | `legacy` \| `uefi` |
| `default_user` | str | |

## CLI

```bash
exoscale-template list-templates
exoscale-template get-template --id <uuid>
exoscale-template create-template --json '{"name": "...", "url": "...", "checksum": "..."}'
exoscale-template delete-template --id <uuid>
```

## Library

```python
from exoscale_connector.resources.template import TemplateClient

templates = TemplateClient(client)
public = templates.list()                      # API default: public
mine = templates.list(visibility="private")
smallest_linux = templates.find_linux()        # smallest public Linux image
```

## Gotchas

- **`size` is in bytes**, unlike instance `disk-size` (GiB) — the same
  unit-of-measure trap as block volumes.
- **`ssh-key-enabled` and `password-enabled` are required on registration** —
  the API returns 400 `missing keys 'ssh-key-enabled', 'password-enabled'` if
  omitted, even though both are optional on the model (they only exist on private
  templates). Set both explicitly: `"ssh-key-enabled": False, "password-enabled": False`.
- **Virtual disk must be ≥ 10 GB** — the import rejects images smaller than 10 GB
  (operation ends in `failure`). qcow2 sparse images are fine; the on-disk file
  stays ~200 KB even at 10 GB virtual size.
- **register/delete live-verified 2026-06-11** via `test_template_register_delete`
  (Tier 1, gated on `EXOSCALE_TEST_TEMPLATE_URL` + `EXOSCALE_TEST_TEMPLATE_CHECKSUM`).
