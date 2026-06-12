#!/usr/bin/env python3
"""Generate the AI reference bundle and the editor skill built from it.

Everything is built from ground truth so it cannot drift from the code:

- the **introspected API surface**: every ``ResourceClient`` subclass with its
  method signatures and docstring summaries, every pydantic model with its
  field/JSON-key/type table — read live from the package in ``src/``
- the **distilled asset-type pages** (``docs/asset-types/*.md``) with their
  live-verified gotchas, embedded verbatim

Artifacts written (all from the same bundle, so one sync check covers all):

- ``docs/llms.txt`` — the paste-anywhere bundle
- ``src/exoscale_connector/_skill/`` — skill shipped inside the wheel,
  installed into a project via ``exoscale-connector skill install``
- ``.claude/skills/exoscale-connector/`` — repo-local copy of the same skill

Usage::

    python scripts/generate_llms_txt.py            # (re)write all artifacts
    python scripts/generate_llms_txt.py --check    # exit 1 if out of sync (CI)

Output is deterministic (sorted, no timestamps) so a plain diff is a reliable
sync check. Stdlib only — no new dependencies.
"""
from __future__ import annotations

import argparse
import dataclasses
import importlib
import inspect
import json
import pkgutil
import re
import sys
from enum import Enum
from pathlib import Path
from typing import Any, Callable, List, Optional, Tuple, Type

REPO_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_PATH = REPO_ROOT / "docs" / "llms.txt"
ASSET_PAGES_DIR = REPO_ROOT / "docs" / "asset-types"
PKG_SKILL_DIR = REPO_ROOT / "src" / "exoscale_connector" / "_skill"
REPO_SKILL_DIR = REPO_ROOT / ".claude" / "skills" / "exoscale-connector"
# Committed upstream OpenAPI snapshot — ground truth for spec-only enums (e.g.
# SKS addons) that have no runtime list endpoint to wrap. Refreshed by the
# weekly upstream drift watch; this generator injects values from it into the
# docs so they never have to be hand-maintained.
UPSTREAM_SPEC = REPO_ROOT / ".github" / "upstream" / "openapi-v2.json"
SKS_PAGE = ASSET_PAGES_DIR / "sks.md"

# Generate from the working tree, not from an installed copy of the package.
sys.path.insert(0, str(REPO_ROOT / "src"))

import exoscale_connector  # noqa: E402
import exoscale_connector.resources as resources_pkg  # noqa: E402
from exoscale_connector import errors as errors_mod  # noqa: E402
from exoscale_connector.client import ExoscaleClient  # noqa: E402
from exoscale_connector.config import ClientConfig  # noqa: E402
from exoscale_connector.models import ExoscaleModel  # noqa: E402
from exoscale_connector.resources._base import ResourceClient  # noqa: E402
from exoscale_connector.wait import wait_for_state  # noqa: E402


# --------------------------------------------------------------------------- #
# Introspection helpers
# --------------------------------------------------------------------------- #
def _doc_summary(obj: Any) -> str:
    """First paragraph of a docstring, collapsed to one line."""
    doc = inspect.getdoc(obj) or ""
    first = doc.split("\n\n", 1)[0]
    return " ".join(first.split())


def _format_signature(func: Callable[..., Any]) -> str:
    """Render a signature, dropping self/cls and the quotes around string annotations."""
    sig = str(inspect.signature(func))
    # `from __future__ import annotations` makes annotations strings; unquote them.
    sig = re.sub(r": '([^']*)'", r": \1", sig)
    sig = re.sub(r" -> '([^']*)'", r" -> \1", sig)
    sig = re.sub(r"^\((self|cls)(, )?", "(", sig)
    return sig


def _fmt_type(tp: Any) -> str:
    """Render a resolved annotation compactly (pydantic field types)."""
    if tp is type(None):
        return "None"
    if isinstance(tp, type):
        return tp.__name__
    text = str(tp).replace("typing.", "")
    text = re.sub(r"<class '(?:[\w.]+\.)?(\w+)'>", r"\1", text)
    return re.sub(r"\bexoscale_connector\.[\w.]+\.(\w+)", r"\1", text)


def _public_methods(
    cls: type, *, owned_by: Optional[type] = None, exclude: Tuple[type, ...] = ()
) -> List[Tuple[str, Callable[..., Any]]]:
    """Public methods of ``cls`` filtered by the class that defines them.

    ``owned_by`` keeps only methods defined on exactly that class; ``exclude``
    drops methods defined on any of the given bases (e.g. the shared
    ``ResourceClient`` CRUD, documented once in its own section).
    """
    out: List[Tuple[str, Callable[..., Any]]] = []
    for name in sorted(dir(cls)):
        if name.startswith("_"):
            continue
        defining = next((k for k in cls.__mro__ if name in vars(k)), None)
        if defining is None or defining in exclude or defining is object:
            continue
        if owned_by is not None and defining is not owned_by:
            continue
        attr = vars(defining)[name]
        if isinstance(attr, (staticmethod, classmethod)):
            out.append((name, attr.__func__))
        elif inspect.isfunction(attr):
            out.append((name, attr))
    return out


def _method_lines(cls: type, **kwargs: Any) -> List[str]:
    lines: List[str] = []
    for name, func in _public_methods(cls, **kwargs):
        lines.append(f"- `{name}{_format_signature(func)}`")
        summary = _doc_summary(func)
        if summary:
            lines.append(f"  {summary}")
    return lines


def _model_lines(cls: Type[ExoscaleModel]) -> List[str]:
    """Field table for a pydantic model: attribute, JSON key, type."""
    lines = [f"#### model `{cls.__name__}`", ""]
    summary = _doc_summary(cls)
    if summary:
        lines += [summary, ""]
    lines += ["| Python attribute | JSON key | Type |", "|---|---|---|"]
    for name, field in cls.model_fields.items():
        alias = field.alias or name
        lines.append(f"| `{name}` | `{alias}` | {_fmt_type(field.annotation)} |")
    lines.append("")
    return lines


def _enum_lines(cls: Type[Enum]) -> List[str]:
    values = ", ".join(f"`{member.value}`" for member in cls)
    lines = [f"#### enum `{cls.__name__}`: {values}"]
    summary = _doc_summary(cls)
    if summary:
        lines.append(summary)
    lines.append("")
    return lines


def _client_lines(cls: type) -> List[str]:
    lines = [f"#### client `{cls.__name__}`", ""]
    summary = _doc_summary(cls)
    if summary:
        lines += [summary, ""]
    if issubclass(cls, ResourceClient):
        facts = [f"API collection: `{getattr(cls, 'collection_path', '?')}`"]
        model = getattr(cls, "model", None)
        if model is not None:
            facts.append(f"resource model: `{model.__name__}`")
        if getattr(cls, "id_field", "id") != "id":
            facts.append(f"keyed by `{cls.id_field}` instead of `id`")
        lines += ["; ".join(facts) + ".", ""]
        lines.append(
            "Inherits the common operations (see above)"
            " plus the methods below, if any."
        )
        method_lines = _method_lines(cls, exclude=(ResourceClient,))
    else:
        method_lines = _method_lines(cls)
    lines += [""] + method_lines + [""]
    return lines


def _resource_module_sections() -> List[str]:
    """One section per asset-type module under ``exoscale_connector.resources``."""
    lines: List[str] = []
    for info in sorted(pkgutil.iter_modules(resources_pkg.__path__), key=lambda m: m.name):
        if info.name.startswith("_"):
            continue
        mod = importlib.import_module(f"exoscale_connector.resources.{info.name}")
        lines += [f"### `exoscale_connector.resources.{info.name}`", ""]
        intro = _doc_summary(mod)
        if intro:
            lines += [intro, ""]
        classes = [
            obj
            for name, obj in sorted(vars(mod).items())
            if inspect.isclass(obj)
            and obj.__module__ == mod.__name__
            and not name.startswith("_")
        ]
        for obj in classes:
            if issubclass(obj, Enum):
                lines += _enum_lines(obj)
        for obj in classes:
            if issubclass(obj, ExoscaleModel):
                lines += _model_lines(obj)
        for obj in classes:
            if not issubclass(obj, (Enum, ExoscaleModel)):
                lines += _client_lines(obj)
    return lines


# --------------------------------------------------------------------------- #
# Asset-type page embedding
# --------------------------------------------------------------------------- #
def _demote_headings(text: str, levels: int = 2) -> str:
    """Shift markdown headings down so embedded pages nest under the bundle TOC."""
    out = []
    in_fence = False
    for line in text.splitlines():
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
        if not in_fence and line.startswith("#"):
            line = "#" * levels + line
        out.append(line)
    return "\n".join(out)


# Marker fence for the spec-derived SKS addon block embedded in sks.md. The
# content between the markers is owned by this generator; everything else on the
# page is hand-written.
ADDON_BLOCK_BEGIN = "<!-- BEGIN GENERATED:sks-addons -->"
ADDON_BLOCK_END = "<!-- END GENERATED:sks-addons -->"


def _spec_addon_enum(spec: dict, schema: str) -> List[str]:
    """Pull the ``addons`` enum for a schema out of the OpenAPI spec, or []."""
    items = (
        spec.get("components", {})
        .get("schemas", {})
        .get(schema, {})
        .get("properties", {})
        .get("addons", {})
        .get("items", {})
    )
    enum = items.get("enum")
    return [v for v in enum if isinstance(v, str)] if isinstance(enum, list) else []


def _sks_addons_block() -> str:
    """Render the marker-fenced SKS addon list from the committed OpenAPI spec.

    SKS addons are a static enum in the spec with no runtime list endpoint, so
    they are sourced here rather than wrapped as a client method. Refreshing the
    committed spec (via the drift watch) regenerates this block.
    """
    spec = json.loads(UPSTREAM_SPEC.read_text(encoding="utf-8"))
    cluster = ", ".join(f"`{a}`" for a in _spec_addon_enum(spec, "sks-cluster"))
    nodepool = ", ".join(f"`{a}`" for a in _spec_addon_enum(spec, "sks-nodepool"))
    return "\n".join(
        [
            ADDON_BLOCK_BEGIN,
            "<!-- Generated from .github/upstream/openapi-v2.json by "
            "scripts/generate_llms_txt.py — do not edit by hand. -->",
            f"- **Cluster** (`SksCluster.addons`): {cluster or '_(none in spec)_'}",
            f"- **Nodepool** (`SksNodepool.addons`): {nodepool or '_(none in spec)_'}",
            ADDON_BLOCK_END,
        ]
    )


def _inject_sks_addons(text: str) -> str:
    """Replace the marker-fenced block in sks.md with freshly generated content.

    Idempotent: re-running with an unchanged spec yields identical text. If the
    markers are absent the page is returned untouched.
    """
    pattern = re.compile(
        re.escape(ADDON_BLOCK_BEGIN) + r".*?" + re.escape(ADDON_BLOCK_END),
        re.DOTALL,
    )
    if not pattern.search(text):
        return text
    block = _sks_addons_block()
    return pattern.sub(lambda _: block, text)


def _load_asset_page(path: Path) -> str:
    """Read an asset page, applying any spec-derived injections it declares."""
    text = path.read_text(encoding="utf-8")
    if path.name == "sks.md":
        text = _inject_sks_addons(text)
    return text


def _asset_page_sections() -> List[str]:
    pages = sorted(p for p in ASSET_PAGES_DIR.glob("*.md") if p.name != "README.md")
    ordered = [ASSET_PAGES_DIR / "README.md"] + pages
    lines: List[str] = []
    for page in ordered:
        lines += [_demote_headings(_load_asset_page(page).rstrip()), ""]
    return lines


# --------------------------------------------------------------------------- #
# Bundle assembly
# --------------------------------------------------------------------------- #
HEADER = """\
# exoscale-connector — AI reference bundle

> Generated by `scripts/generate_llms_txt.py` from the package source and the
> live-verified asset-type docs. Do not edit by hand — regenerate instead.
> Package version: {version}.

`exoscale-connector` is a clean, typed, reusable Python connector for the
Exoscale APIv2. Runtime dependencies are just `requests` + `pydantic` v2
(Object Storage support optionally adds `boto3` via the `[sos]` extra).
Install with `pip install exoscale-connector`.

This file is self-contained context for an AI assistant. Everything in it is
generated from code or backed by live tests against a real Exoscale tenant —
when guidance here contradicts the OpenAPI spec, this file reflects observed
live behaviour. Cite real methods from the API surface below; do not invent
methods or fields.

## Core usage

```python
from exoscale_connector import ExoscaleClient
from exoscale_connector.resources.security_group import SecurityGroupClient

client = ExoscaleClient.from_env(zone="de-fra-1")
groups = SecurityGroupClient(client).list()
```

Conventions that apply everywhere:

- **Authentication is env-based only**: `EXOSCALE_API_KEY` /
  `EXOSCALE_API_SECRET` / `EXOSCALE_ZONE`. Nothing is read from disk or
  hardcoded; inject credentials with any secret manager.
- **snake_case ↔ kebab-case**: every model maps Python snake_case attributes
  to the API's kebab-case JSON keys automatically (`flow_direction` ↔
  `flow-direction`). Build payloads with either typed models or plain dicts
  using the kebab-case keys.
- **Unknown server fields pass through** (`extra="allow"`), so models keep
  working when the API adds fields.
- **Async operations are awaited by default** — mutating calls poll the
  operation and return the settled resource; pass `wait=False` to get the
  `Operation` envelope back immediately.
- **`ensure()` is idempotent get-or-create by name** — provisioning scripts
  are re-runnable by construction.
- **Catalogue knowledge is discovered, never hardcoded**: zones, instance
  types, and templates are queried live (`ZoneClient`, `InstanceTypeClient`,
  `TemplateClient`), never from baked-in enums.
- **CLI**: each asset type also has a CLI binary (e.g.
  `exoscale-security-group`), all namespaced under `exoscale-connector`.
  JSON to stdout, errors to stderr, exit 0/1/2 (success/API error/usage).
"""


SKILL_MD = """\
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
"""


def generate_bundle() -> str:
    lines: List[str] = [HEADER.format(version=exoscale_connector.__version__), ""]

    lines += ["## Core client", "", _doc_summary(ExoscaleClient), ""]
    lines += _method_lines(ExoscaleClient, owned_by=ExoscaleClient)
    lines += ["", "`ClientConfig` fields (all overridable via environment):", ""]
    for field in dataclasses.fields(ClientConfig):
        lines.append(f"- `{field.name}`: {_fmt_type(field.type)}")
    lines += ["", "### Errors", ""]
    for name, obj in sorted(vars(errors_mod).items()):
        if inspect.isclass(obj) and issubclass(obj, Exception) and not name.startswith("_"):
            lines.append(f"- `{name}` — {_doc_summary(obj)}")
    lines += ["", "### Waiting helpers", ""]
    lines.append(f"- `wait_for_state{_format_signature(wait_for_state)}`")
    lines.append(f"  {_doc_summary(wait_for_state)}")

    lines += ["", "## Common operations — every resource client", ""]
    lines += [_doc_summary(ResourceClient), ""]
    lines += _method_lines(ResourceClient, owned_by=ResourceClient)

    lines += ["", "## IAM policy expression helpers (`exoscale_connector.iam_expr`)", ""]
    iam_expr = importlib.import_module("exoscale_connector.iam_expr")
    for name, obj in sorted(vars(iam_expr).items()):
        if inspect.isfunction(obj) and obj.__module__ == iam_expr.__name__ \
                and not name.startswith("_"):
            lines.append(f"- `{name}{_format_signature(obj)}` — {_doc_summary(obj)}")

    lines += ["", "## API surface by asset type", ""]
    lines += _resource_module_sections()

    lines += ["## Asset-type reference pages (live-verified)", ""]
    lines += _asset_page_sections()

    return "\n".join(lines).rstrip() + "\n"


def artifacts() -> "dict[Path, str]":
    """Every generated file and its expected content, keyed by absolute path."""
    bundle = generate_bundle()
    return {
        OUTPUT_PATH: bundle,
        # sks.md carries a spec-derived addon block, so it is partly generated:
        # keep its injected form under the same sync gate as everything else.
        SKS_PAGE: _load_asset_page(SKS_PAGE),
        PKG_SKILL_DIR / "SKILL.md": SKILL_MD,
        PKG_SKILL_DIR / "reference.md": bundle,
        REPO_SKILL_DIR / "SKILL.md": SKILL_MD,
        REPO_SKILL_DIR / "reference.md": bundle,
    }


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument(
        "--check",
        action="store_true",
        help="verify the generated artifacts are in sync with the code; exit 1 if not",
    )
    args = parser.parse_args(argv)

    if args.check:
        stale = [
            path
            for path, content in artifacts().items()
            if not path.exists() or path.read_text(encoding="utf-8") != content
        ]
        if stale:
            names = ", ".join(str(p.relative_to(REPO_ROOT)) for p in stale)
            print(
                f"Out of sync with the code: {names}. "
                "Regenerate with: python scripts/generate_llms_txt.py",
                file=sys.stderr,
            )
            return 1
        print("All generated artifacts are in sync.")
        return 0

    for path, content in artifacts().items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        print(f"Wrote {path.relative_to(REPO_ROOT)} ({len(content.splitlines())} lines).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
