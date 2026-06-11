#!/usr/bin/env python3
"""Print the APIv2 path → connector module → doc page mapping as markdown.

Used by the upstream-drift workflow to make its issues agent-ready: a spec
changelog entry under e.g. ``/block-storage`` maps straight to
``resources/block_volume.py`` and ``docs/asset-types/block-volume.md``.
Derived from ``collection_path`` introspection (same ground-truth approach
as ``generate_llms_txt.py``), so it cannot drift from the code.
"""
from __future__ import annotations

import importlib
import inspect
import pkgutil
import sys
from pathlib import Path
from typing import List, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent

# Generate from the working tree, not from an installed copy of the package.
sys.path.insert(0, str(REPO_ROOT / "src"))

import exoscale_connector.resources as resources_pkg  # noqa: E402
from exoscale_connector.resources._base import ResourceClient  # noqa: E402


def mapping_rows() -> List[Tuple[str, str, str, str]]:
    """(spec path prefix, client class, module path, doc page) per asset type."""
    rows = []
    for info in sorted(pkgutil.iter_modules(resources_pkg.__path__), key=lambda m: m.name):
        if info.name.startswith("_"):
            continue
        mod = importlib.import_module(f"exoscale_connector.resources.{info.name}")
        for name, obj in sorted(vars(mod).items()):
            if (
                inspect.isclass(obj)
                and issubclass(obj, ResourceClient)
                and obj is not ResourceClient
                and obj.__module__ == mod.__name__
            ):
                rows.append(
                    (
                        f"/{obj.collection_path}",
                        name,
                        f"src/exoscale_connector/resources/{info.name}.py",
                        f"docs/asset-types/{info.name.replace('_', '-')}.md",
                    )
                )
    return rows


def main() -> int:
    print("| Spec path prefix | Client | Module | Doc page |")
    print("|---|---|---|---|")
    for path, client, module, doc in mapping_rows():
        print(f"| `{path}` | `{client}` | `{module}` | `{doc}` |")
    print()
    print(
        "_Object Storage (SOS) is S3-compatible and outside the APIv2 spec — "
        "`docs/asset-types/object-storage.md` is not covered by this watch._"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
