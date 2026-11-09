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
| `ssh_key_enabled` / `password_enabled` | bool | required on registration (see gotcha) |
| `created_at` | str | |
| `maintainer` | str | read-only |
| `application_consistent_snapshot_enabled` | bool | QEMU guest agent present |
| `zones` | list[str] | zones the template is available in |

## CLI

```bash
exoscale-template list-templates
exoscale-template get-template --id <uuid>
exoscale-template find-template --name <name>
exoscale-template create-template --json '{"name": "...", "url": "...", "checksum": "...", "ssh-key-enabled": false, "password-enabled": false}'
exoscale-template delete-template --id <uuid>
```

## Library

```python
from exoscale_connector.resources.template import TemplateClient

templates = TemplateClient(client)
public = templates.list()                      # API default: public
mine = templates.list(visibility="private")
smallest_linux = templates.find_linux()        # smallest public Linux image

# Copy a private template to another zone; it keeps the same id there
templates.copy(template_id, "ch-gva-2")
copy = TemplateClient(client, zone="ch-gva-2").get(template_id)
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
- **`copy(id, target_zone)` keeps the template id.** It is `POST
  /template/{id}` with `{"target-zone": {"name": ...}}`, and
  `operation.reference_id` is the *same* id. One template then exists in
  several zones, and **deleting it in any zone removes it everywhere**
  (observed 2026-11-09: after a delete in the target zone the source zone
  returned 404). `Template.zones` was empty on the read.
