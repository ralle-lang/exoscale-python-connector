#!/usr/bin/env python3
"""Module -> APIv2 operations map, self-enforced against the code.

Two jobs:

1. :data:`MODULE_SIBLING_OPERATIONS` declares, per resource module, the APIv2
   path templates it calls that do **not** sit under the module's own
   ``collection_path`` (sibling endpoints such as ``sks-cluster-version`` or the
   per-type ``dbaas-*`` paths). Everything under a module's collection path is
   attributed automatically and needs no declaration. ``test_drift_operations``
   fails if the code calls a sibling endpoint missing from this map, so it cannot
   silently fall behind the code — the same self-enforcing contract as the
   ``llms.txt`` sync test.

2. :func:`affected_modules` maps a set of changed spec paths (computed by the
   weekly upstream-drift workflow from the old vs new OpenAPI snapshot) to the
   connector modules that touch them, so a drift issue can say *which* modules to
   review instead of dumping the whole mapping table.

Endpoints are discovered from the code with :mod:`ast` (the first argument of
every ``self.client.get/post/put/delete(...)`` call), so discovery tracks the
code without hand-maintenance; only the small set of cross-collection siblings is
declared by hand here.
"""
from __future__ import annotations

import argparse
import ast
import importlib
import inspect
import json
import pkgutil
import sys
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent
RESOURCES_DIR = REPO_ROOT / "src" / "exoscale_connector" / "resources"

# Generate from the working tree, not from an installed copy of the package.
sys.path.insert(0, str(REPO_ROOT / "src"))

import exoscale_connector.resources as resources_pkg  # noqa: E402
from exoscale_connector.resources._base import ResourceClient  # noqa: E402

# Sibling endpoints a module calls that live outside its own collection path.
# A trailing ``*`` on a segment matches any segment with that prefix (used for
# the per-service-type ``dbaas-postgres`` / ``dbaas-mysql`` / ... paths). Keep
# this minimal: only declare what the collection-path prefix can't already
# attribute. The unit test fails if the code grows a sibling not listed here.
MODULE_SIBLING_OPERATIONS: Dict[str, List[str]] = {
    # Snapshot is created through the instance collection, not snapshot/.
    "snapshot": ["instance/{}:create-snapshot"],
    # A block-volume snapshot is created through the block-storage collection.
    "block_volume_snapshot": ["block-storage/{}:create-snapshot"],
    # SKS version discovery and kubeconfig live beside, not under, sks-cluster/.
    "sks": ["sks-cluster-version", "sks-cluster-kubeconfig"],
    # DBaaS mutations use per-service-type paths (dbaas-postgres, dbaas-mysql, …)
    # plus the dbaas-service-type catalogue — all outside dbaas-service/.
    "dbaas": ["dbaas-*"],
}


# --------------------------------------------------------------------------- #
# Path / template normalisation
# --------------------------------------------------------------------------- #
def _normalize(path: str) -> str:
    """Canonicalise a spec path or rendered template: no leading slash, ``{}`` vars."""
    path = path.strip()
    if path.startswith("/"):
        path = path[1:]
    # Collapse any ``{anything}`` placeholder to a bare ``{}``.
    out: List[str] = []
    depth = 0
    for ch in path:
        if ch == "{":
            if depth == 0:
                out.append("{}")
            depth += 1
        elif ch == "}":
            depth = max(0, depth - 1)
        elif depth == 0:
            out.append(ch)
    return "".join(out)


def _segments(template: str) -> List[str]:
    return [s for s in _normalize(template).split("/") if s != ""]


def _seg_matches(tmpl_seg: str, path_seg: str) -> bool:
    if tmpl_seg == path_seg or tmpl_seg == "{}":
        return True
    if tmpl_seg.endswith("*"):
        return path_seg.startswith(tmpl_seg[:-1])
    return False


def template_covers(template: str, path: str) -> bool:
    """True if ``template`` attributes ``path`` (segment-wise prefix match).

    ``{}`` matches any single segment; a trailing ``*`` matches any segment with
    that prefix. ``path`` may be deeper than ``template`` (sub-resources), but
    every template segment must match the aligned path segment — so a base path
    like ``sks-cluster`` does NOT swallow the sibling ``sks-cluster-version``.
    """
    t_segs = _segments(template)
    p_segs = _segments(path)
    if len(t_segs) > len(p_segs):
        return False
    return all(_seg_matches(t, p) for t, p in zip(t_segs, p_segs))


# --------------------------------------------------------------------------- #
# Code introspection: collection paths + discovered client-call endpoints
# --------------------------------------------------------------------------- #
def _module_collection_paths() -> Dict[str, List[str]]:
    """Module stem -> the ``collection_path`` of every ResourceClient it defines."""
    out: Dict[str, List[str]] = {}
    for info in sorted(pkgutil.iter_modules(resources_pkg.__path__), key=lambda m: m.name):
        if info.name.startswith("_"):
            continue
        mod = importlib.import_module(f"exoscale_connector.resources.{info.name}")
        paths: List[str] = []
        for _, obj in sorted(vars(mod).items()):
            if (
                inspect.isclass(obj)
                and issubclass(obj, ResourceClient)
                and obj is not ResourceClient
                and obj.__module__ == mod.__name__
            ):
                cp = getattr(obj, "collection_path", None)
                if isinstance(cp, str):
                    paths.append(cp)
        if paths:
            out[info.name] = sorted(set(paths))
    return out


class _EndpointVisitor(ast.NodeVisitor):
    """Collect the first-arg endpoint of every ``self.client.<verb>(...)`` call."""

    _VERBS = {"get", "post", "put", "delete"}

    def __init__(self, collection_paths: List[str]) -> None:
        # Resolve ``self.collection_path`` to the module's path. Multiple clients
        # in one module are rare; the first declared path is the resolution hint.
        self.collection_path = collection_paths[0] if collection_paths else ""
        self.endpoints: Set[str] = set()
        self._locals: Dict[str, str] = {}

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        saved = self._locals
        self._locals = {}
        for stmt in ast.walk(node):
            if (
                isinstance(stmt, ast.Assign)
                and len(stmt.targets) == 1
                and isinstance(stmt.targets[0], ast.Name)
            ):
                rendered = self._render(stmt.value)
                if rendered is not None:
                    self._locals[stmt.targets[0].id] = rendered
        self.generic_visit(node)
        self._locals = saved

    def visit_Call(self, node: ast.Call) -> None:
        func = node.func
        if (
            isinstance(func, ast.Attribute)
            and func.attr in self._VERBS
            and isinstance(func.value, ast.Attribute)
            and func.value.attr == "client"
            and isinstance(func.value.value, ast.Name)
            and func.value.value.id == "self"
            and node.args
        ):
            rendered = self._render(node.args[0])
            if rendered is not None:
                self.endpoints.add(rendered)
        self.generic_visit(node)

    def _is_self_collection_path(self, node: ast.AST) -> bool:
        return (
            isinstance(node, ast.Attribute)
            and node.attr == "collection_path"
            and isinstance(node.value, ast.Name)
            and node.value.id == "self"
        )

    def _render(self, node: ast.AST) -> Optional[str]:
        if self._is_self_collection_path(node):
            return self.collection_path
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return _normalize(node.value)
        if isinstance(node, ast.Name):
            return self._locals.get(node.id)
        if isinstance(node, ast.JoinedStr):
            parts: List[str] = []
            for value in node.values:
                if isinstance(value, ast.Constant) and isinstance(value.value, str):
                    parts.append(value.value)
                elif isinstance(value, ast.FormattedValue) and self._is_self_collection_path(
                    value.value
                ):
                    parts.append(self.collection_path)
                else:
                    parts.append("{}")
            return _normalize("".join(parts))
        return None


def discovered_operations() -> Dict[str, List[str]]:
    """Module stem -> sorted endpoints the module's code calls on ``self.client``."""
    collection_paths = _module_collection_paths()
    out: Dict[str, List[str]] = {}
    for path in sorted(RESOURCES_DIR.glob("*.py")):
        if path.name.startswith("_"):
            continue
        stem = path.stem
        visitor = _EndpointVisitor(collection_paths.get(stem, []))
        visitor.visit(ast.parse(path.read_text(encoding="utf-8")))
        if visitor.endpoints:
            out[stem] = sorted(visitor.endpoints)
    return out


def undeclared_siblings() -> Dict[str, List[str]]:
    """Module -> endpoints it calls that neither its collection path nor the
    declared siblings attribute. Must be empty; the unit test enforces it."""
    collection_paths = _module_collection_paths()
    out: Dict[str, List[str]] = {}
    for stem, endpoints in discovered_operations().items():
        own = collection_paths.get(stem, [])
        siblings = MODULE_SIBLING_OPERATIONS.get(stem, [])
        missing = [
            ep
            for ep in endpoints
            if not any(template_covers(cp, ep) for cp in own)
            and not any(template_covers(sib, ep) for sib in siblings)
        ]
        if missing:
            out[stem] = missing
    return out


# --------------------------------------------------------------------------- #
# Spec diff -> affected modules
# --------------------------------------------------------------------------- #
def changed_spec_paths(base: dict, revision: dict) -> Dict[str, str]:
    """Normalised spec path -> ``added`` | ``removed`` | ``changed``."""
    base_paths = base.get("paths", {}) or {}
    rev_paths = revision.get("paths", {}) or {}
    out: Dict[str, str] = {}
    for raw in sorted(set(base_paths) | set(rev_paths)):
        key = _normalize(raw)
        if raw not in base_paths:
            out[key] = "added"
        elif raw not in rev_paths:
            out[key] = "removed"
        elif json.dumps(base_paths[raw], sort_keys=True) != json.dumps(
            rev_paths[raw], sort_keys=True
        ):
            out[key] = "changed"
    return out


def affected_modules(
    changed: Dict[str, str],
) -> Tuple[Dict[str, List[Tuple[str, str]]], List[Tuple[str, str]]]:
    """Group changed paths by the connector module that owns them.

    Returns ``(by_module, unmatched)`` where ``by_module`` maps a module path to
    ``(spec_path, status)`` rows and ``unmatched`` lists changed paths no module
    touches (surfaced so nothing is silently dropped).
    """
    collection_paths = _module_collection_paths()
    siblings = MODULE_SIBLING_OPERATIONS
    by_module: Dict[str, List[Tuple[str, str]]] = {}
    unmatched: List[Tuple[str, str]] = []
    for path, status in sorted(changed.items()):
        owners: Set[str] = set()
        for stem, own in collection_paths.items():
            templates = list(own) + list(siblings.get(stem, []))
            if any(template_covers(t, path) for t in templates):
                owners.add(f"src/exoscale_connector/resources/{stem}.py")
        if owners:
            for module in owners:
                by_module.setdefault(module, []).append((path, status))
        else:
            unmatched.append((path, status))
    return by_module, unmatched


def render_affected_markdown(base: dict, revision: dict) -> str:
    changed = changed_spec_paths(base, revision)
    by_module, unmatched = affected_modules(changed)
    lines: List[str] = []
    if not changed:
        return "_No path-level spec changes detected._\n"
    if by_module:
        lines.append("| Connector module | Changed spec path | Change |")
        lines.append("|---|---|---|")
        for module in sorted(by_module):
            for path, status in by_module[module]:
                lines.append(f"| `{module}` | `/{path}` | {status} |")
    else:
        lines.append("_No changed paths map to a connector module._")
    if unmatched:
        lines.append("")
        lines.append(
            "Changed paths not used by any connector module "
            "(informational — no module to review):"
        )
        lines.append("")
        for path, status in unmatched:
            lines.append(f"- `/{path}` ({status})")
    return "\n".join(lines) + "\n"


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument(
        "--affected",
        nargs=2,
        metavar=("BASE_SPEC", "REVISION_SPEC"),
        help="two OpenAPI JSON files (old, new); print the affected-modules summary",
    )
    args = parser.parse_args(argv)

    if args.affected:
        base = json.loads(Path(args.affected[0]).read_text(encoding="utf-8"))
        revision = json.loads(Path(args.affected[1]).read_text(encoding="utf-8"))
        sys.stdout.write(render_affected_markdown(base, revision))
        return 0

    # Default: report any undeclared siblings (handy locally; the test enforces it).
    missing = undeclared_siblings()
    if missing:
        for module, endpoints in missing.items():
            print(f"{module}: undeclared sibling operations: {endpoints}", file=sys.stderr)
        return 1
    print("All client-call endpoints are attributed to a module.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
