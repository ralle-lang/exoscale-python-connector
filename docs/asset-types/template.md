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
- **Live verification:** list/get and `find_linux` mirror the selection logic
  the Tier 3 fixtures have always used live; register/delete are implemented
  from the API reference and **pending live verification**.
