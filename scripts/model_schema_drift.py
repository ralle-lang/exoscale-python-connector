#!/usr/bin/env python3
"""Pydantic model <-> APIv2 OpenAPI schema field drift, self-enforced against the spec.

Diffs every resource pydantic model's fields against the committed APIv2 OpenAPI
snapshot (``.github/upstream/openapi-v2.json``) schema for that model's endpoint and
fails on drift. Three things fail the build:

* **model-only** fields — a model field whose JSON alias is absent from the schema
  (a rename, a removed/deprecated field, or a live-API field the spec lacks);
* **type mismatch** — a field present on both sides whose JSON type family differs;
* **missing-required** — a field the schema marks ``required`` that the model omits.

Spec fields the model merely *omits* (and that are not required) are reported as
**informational only**: the models are a deliberately curated subset and
``ExoscaleModel`` sets ``extra="allow"``, so unmodelled response fields are tolerated
by design.

Self-enforcing, the same contract as ``drift_operations`` and the ``llms.txt`` sync
test:

* every resource model must resolve to a schema — via its client ``collection_path``,
  the small :data:`SCHEMA_ALIASES` map, or an explicit :data:`EXEMPT_MODELS` entry.
  An unresolved model fails the test, so a new asset type can't slip past unchecked;
* :data:`ALLOWED_DIVERGENCES` records each intentional, live-verified mismatch with a
  reason. A *stale* allowlist entry (one that matches no real mismatch) also fails the
  test, so the allowlist can't quietly rot.

Schema resolution follows ``$ref`` and flattens ``allOf`` / ``anyOf`` / ``oneOf``
composition. Type comparison is by coarse JSON family (string / number / boolean /
array / object), so idiomatic typing choices don't generate noise — only a genuine
family change (e.g. string -> object) is flagged.
"""
from __future__ import annotations

import argparse
import importlib
import inspect
import json
import pkgutil
import sys
import typing
from pathlib import Path
from typing import Dict, FrozenSet, List, Optional, Set, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent
UPSTREAM_SPEC = REPO_ROOT / ".github" / "upstream" / "openapi-v2.json"

# Generate from the working tree, not from an installed copy of the package.
sys.path.insert(0, str(REPO_ROOT / "src"))

import exoscale_connector.resources as resources_pkg  # noqa: E402
from exoscale_connector.models import ExoscaleModel, to_kebab  # noqa: E402
from exoscale_connector.resources._base import ResourceClient  # noqa: E402

# --------------------------------------------------------------------------- #
# Mapping: model -> schema. Inferred from collection_path / class name; only the
# cases the inference can't reach are declared here. Keep both maps minimal —
# the test fails on a stale entry or an unresolved model.
# --------------------------------------------------------------------------- #

# Models that have no APIv2 OpenAPI schema and are not diffed, with the reason.
EXEMPT_MODELS: Dict[str, str] = {
    "Bucket": "S3-compatible object storage, not part of the APIv2 OpenAPI spec",
    "S3Object": "S3-compatible object storage, not part of the APIv2 OpenAPI spec",
    "DBaaSService": (
        "flattened superset of the dbaas-service-* discriminated union "
        "(dbaas-service-pg / -mysql / -kafka / ...); no single 1:1 schema to diff against"
    ),
    "DBaaSConnectionInfo": (
        "synthetic connection-info helper assembled by the client; no spec schema"
    ),
}

# Model class name -> schema name, for the cases collection_path / kebab-casing
# can't derive on their own.
SCHEMA_ALIASES: Dict[str, str] = {
    # collection_path is "block-storage"; the resource schema is the -volume one.
    "BlockVolume": "block-storage-volume",
    # No "api-key" schema exists; the get/list shape is iam-api-key (the create
    # response iam-api-key-created additionally carries the one-time secret).
    "ApiKey": "iam-api-key",
    # Acronym/compound names whose naive kebab-casing doesn't hit the schema.
    "DnsRecord": "dns-domain-record",
    "SshKeyReference": "ssh-key-ref",
    "BlockVolumeSnapshotRef": "block-storage-snapshot-ref",
    "ElasticIPHealthcheck": "elastic-ip-healthcheck",
    "IAMPolicy": "iam-policy",
    "IAMPolicyService": "iam-service-policy",
    "IAMPolicyRule": "iam-service-policy-rule",
    # VPC sub-resources: the spec schemas are the unprefixed `subnet` / `route`.
    "VpcSubnet": "subnet",
    "VpcRoute": "route",
    # KMS: collection_path "kms-key" maps to an empty stub; the detail response
    # (superset of the list entry) is the schema to diff against.
    "KmsKey": "get-kms-key-response",
    "KeyRotationConfig": "key-rotation-config",
}

# Intentional, live-verified divergences. model name -> {json-alias: reason}. A
# field listed here is excluded from the model-only / type-mismatch /
# missing-required failures. Every entry must match a real mismatch (else the
# stale-entry test fails), so this stays an honest record of known deltas.
ALLOWED_DIVERGENCES: Dict[str, Dict[str, str]] = {
    "ApiKey": {
        "role": "convenience Reference to the scoped role; spec exposes role-id only",
        "secret": "one-time create secret (spec schema iam-api-key-created); never on read",
    },
    "BlockVolumeSnapshotRef": {
        "name": "live API includes the snapshot name in the ref; spec ref lists id only",
    },
    "DnsDomain": {
        "state": "live response field; spec dns-domain lists created-at/id/unicode-name only",
        "updated-at": "live response field absent from the spec dns-domain schema",
    },
    "IAMUser": {
        "role-id": "flattened convenience alongside the role Reference; spec nests role only",
    },
    "InstancePool": {
        "created-at": "live response field absent from the spec instance-pool schema",
    },
    # Documented in docs/asset-types/load-balancer.md (Gotchas): the model
    # flattens the nested spec `healthcheck` object into healthcheck-* fields.
    "LoadBalancerService": {
        f"healthcheck-{suffix}": "model flattens the nested spec `healthcheck` object (LB gotchas)"
        for suffix in ("mode", "port", "uri", "interval", "timeout", "retries", "tls-sni")
    },
    "SSHKey": {
        "public-key": "create-request field; the spec ssh-key response schema omits it",
    },
    "SksCluster": {
        # Documented in docs/asset-types/sks.md (Gotchas): create field is `level`.
        "service-level": "exposes the cluster `level` concept; spec property is named level",
    },
}


# --------------------------------------------------------------------------- #
# Spec loading + schema resolution
# --------------------------------------------------------------------------- #
def load_schemas(spec_path: Path) -> Dict[str, dict]:
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    return spec.get("components", {}).get("schemas", {}) or {}


_FAMILY_BY_TYPE = {
    "string": "string",
    "integer": "number",
    "number": "number",
    "boolean": "boolean",
    "array": "array",
    "object": "object",
}


def _schema_family(node: dict, schemas: Dict[str, dict], seen: FrozenSet[str]) -> str:
    """Coarse JSON family of a property schema, dereferencing a single ``$ref``."""
    if not isinstance(node, dict):
        return "wildcard"
    ref = node.get("$ref")
    if ref:
        name = ref.split("/")[-1]
        if name in seen:
            return "object"
        return _schema_family(schemas.get(name, {}), schemas, seen | {name})
    type_ = node.get("type")
    if isinstance(type_, str) and type_ in _FAMILY_BY_TYPE:
        return _FAMILY_BY_TYPE[type_]
    enum = node.get("enum")
    if isinstance(enum, list) and enum:
        if all(isinstance(v, str) for v in enum):
            return "string"
        if all(isinstance(v, bool) for v in enum):
            return "boolean"
        if all(isinstance(v, (int, float)) for v in enum):
            return "number"
        return "wildcard"
    if any(k in node for k in ("properties", "allOf", "anyOf", "oneOf")):
        return "object"
    return "wildcard"


def resolve_schema(
    node: dict, schemas: Dict[str, dict], seen: FrozenSet[str] = frozenset()
) -> Tuple[Dict[str, str], Set[str]]:
    """Flatten a schema to ``(properties{name: family}, required{name})``.

    Follows ``$ref`` and merges ``allOf``; for ``anyOf`` / ``oneOf`` it unions the
    member properties (a field present in any variant counts as known) but takes no
    ``required`` from the union, since a union member's requirement isn't unconditional.
    """
    props: Dict[str, str] = {}
    required: Set[str] = set()
    if not isinstance(node, dict):
        return props, required

    ref = node.get("$ref")
    if ref:
        name = ref.split("/")[-1]
        if name in seen:
            return props, required
        return resolve_schema(schemas.get(name, {}), schemas, seen | {name})

    for sub in node.get("allOf", []) or []:
        sub_props, sub_required = resolve_schema(sub, schemas, seen)
        props.update(sub_props)
        required |= sub_required
    for key in ("anyOf", "oneOf"):
        for sub in node.get(key, []) or []:
            sub_props, _ = resolve_schema(sub, schemas, seen)
            props.update(sub_props)

    properties = node.get("properties")
    if isinstance(properties, dict):
        for prop_name, prop_schema in properties.items():
            props[prop_name] = _schema_family(prop_schema, schemas, seen)
        req = node.get("required")
        if isinstance(req, list):
            required |= {r for r in req if isinstance(r, str)}
    return props, required


# --------------------------------------------------------------------------- #
# Model introspection
# --------------------------------------------------------------------------- #
def _py_family(annotation: object) -> str:
    """Coarse JSON family of a pydantic field annotation."""
    origin = typing.get_origin(annotation)
    args = typing.get_args(annotation)
    if origin is typing.Union:
        non_none = [a for a in args if a is not type(None)]
        if len(non_none) == 1:
            return _py_family(non_none[0])
        return "wildcard"
    if origin in (list, set, tuple, frozenset):
        return "array"
    if origin is dict:
        return "object"
    if inspect.isclass(annotation):
        if annotation is bool:
            return "boolean"
        if annotation is str:
            return "string"
        if annotation in (int, float):
            return "number"
        if annotation is list:
            return "array"
        if annotation is dict:
            return "object"
        if issubclass(annotation, ExoscaleModel):
            return "object"
    return "wildcard"


def model_field_families(model: type) -> Dict[str, str]:
    """JSON alias -> family for every declared field of a pydantic model."""
    out: Dict[str, str] = {}
    for name, field in model.model_fields.items():
        alias = field.alias or to_kebab(name)
        out[alias] = _py_family(field.annotation)
    return out


def _resource_models() -> List[type]:
    """Every concrete ``ExoscaleModel`` subclass declared in resources/*.py."""
    models: List[type] = []
    for info in sorted(pkgutil.iter_modules(resources_pkg.__path__), key=lambda m: m.name):
        if info.name.startswith("_"):
            continue
        mod = importlib.import_module(f"exoscale_connector.resources.{info.name}")
        for _, obj in sorted(vars(mod).items()):
            if (
                inspect.isclass(obj)
                and issubclass(obj, ExoscaleModel)
                and obj is not ExoscaleModel
                and obj.__module__ == mod.__name__
            ):
                models.append(obj)
    return models


def _collection_path_by_model() -> Dict[str, str]:
    """Model class name -> its client's collection_path (for primary resources)."""
    out: Dict[str, str] = {}
    for info in pkgutil.iter_modules(resources_pkg.__path__):
        if info.name.startswith("_"):
            continue
        mod = importlib.import_module(f"exoscale_connector.resources.{info.name}")
        for _, obj in vars(mod).items():
            if (
                inspect.isclass(obj)
                and issubclass(obj, ResourceClient)
                and obj is not ResourceClient
                and obj.__module__ == mod.__name__
            ):
                model = getattr(obj, "model", None)
                cp = getattr(obj, "collection_path", None)
                if model is not None and isinstance(cp, str):
                    out[model.__name__] = cp
    return out


def schema_name_for(
    model_name: str, cp_by_model: Dict[str, str], schemas: Dict[str, dict]
) -> Tuple[str, Optional[str]]:
    """Resolve a model to ``("exempt"|"schema"|"unresolved", schema_name|None)``."""
    if model_name in EXEMPT_MODELS:
        return ("exempt", None)
    if model_name in SCHEMA_ALIASES:
        return ("schema", SCHEMA_ALIASES[model_name])
    cp = cp_by_model.get(model_name)
    if cp and cp in schemas:
        return ("schema", cp)
    guess = to_kebab(_camel_to_snake(model_name))
    if guess in schemas:
        return ("schema", guess)
    return ("unresolved", None)


def _camel_to_snake(name: str) -> str:
    out: List[str] = []
    for i, ch in enumerate(name):
        if ch.isupper() and i > 0 and not name[i - 1].isupper():
            out.append("_")
        out.append(ch.lower())
    return "".join(out)


# --------------------------------------------------------------------------- #
# Diffing
# --------------------------------------------------------------------------- #
class ModelDrift:
    """The drift findings for one model, after applying the allowlist."""

    def __init__(self, model_name: str, schema: str) -> None:
        self.model_name = model_name
        self.schema = schema
        self.model_only: List[str] = []  # fail: alias not in schema
        self.type_mismatch: List[Tuple[str, str, str]] = []  # fail: (alias, model, spec)
        self.missing_required: List[str] = []  # fail: required spec field absent from model
        self.missing_optional: List[str] = []  # informational only

    @property
    def has_failures(self) -> bool:
        return bool(self.model_only or self.type_mismatch or self.missing_required)

    def used_allow_aliases(self) -> Set[str]:
        """Aliases that the allowlist actually suppressed for this model."""
        return _ALLOW_USAGE.get(self.model_name, set())


# Records which allowlist aliases suppressed a real mismatch this run, so the
# stale-entry test can flag entries that suppressed nothing.
_ALLOW_USAGE: Dict[str, Set[str]] = {}


def diff_model(
    model: type, schemas: Dict[str, dict], cp_by_model: Dict[str, str]
) -> Optional[ModelDrift]:
    """Diff one model against its schema. Returns ``None`` for exempt models."""
    kind, schema = schema_name_for(model.__name__, cp_by_model, schemas)
    if kind != "schema" or schema is None:
        return None
    props, required = resolve_schema(schemas.get(schema, {}), schemas)
    fields = model_field_families(model)
    allow = ALLOWED_DIVERGENCES.get(model.__name__, {})
    used: Set[str] = set()

    drift = ModelDrift(model.__name__, schema)
    for alias, family in fields.items():
        if alias not in props:
            if alias in allow:
                used.add(alias)
            else:
                drift.model_only.append(alias)
        elif family != "wildcard" and props[alias] != "wildcard" and family != props[alias]:
            if alias in allow:
                used.add(alias)
            else:
                drift.type_mismatch.append((alias, family, props[alias]))
    for prop in sorted(props):
        if prop in fields:
            continue
        if prop in required:
            if prop in allow:
                used.add(prop)
            else:
                drift.missing_required.append(prop)
        else:
            drift.missing_optional.append(prop)

    drift.model_only.sort()
    drift.missing_required.sort()
    _ALLOW_USAGE[model.__name__] = used
    return drift


def all_drift(schemas: Dict[str, dict]) -> List[ModelDrift]:
    cp_by_model = _collection_path_by_model()
    out: List[ModelDrift] = []
    for model in _resource_models():
        drift = diff_model(model, schemas, cp_by_model)
        if drift is not None:
            out.append(drift)
    return sorted(out, key=lambda d: d.model_name)


def unresolved_models(schemas: Dict[str, dict]) -> List[str]:
    cp_by_model = _collection_path_by_model()
    out: List[str] = []
    for model in _resource_models():
        kind, _ = schema_name_for(model.__name__, cp_by_model, schemas)
        if kind == "unresolved":
            out.append(model.__name__)
    return sorted(out)


def stale_allowlist_entries(schemas: Dict[str, dict]) -> Dict[str, List[str]]:
    """Allowlisted (model, alias) pairs that suppressed no real mismatch this run."""
    all_drift(schemas)  # populates _ALLOW_USAGE as a side effect
    cp_by_model = _collection_path_by_model()
    known = {m.__name__ for m in _resource_models()}
    out: Dict[str, List[str]] = {}
    for model_name, aliases in ALLOWED_DIVERGENCES.items():
        if model_name not in known:
            out.setdefault(model_name, []).append("<model no longer exists>")
            continue
        kind, _ = schema_name_for(model_name, cp_by_model, schemas)
        if kind != "schema":
            out.setdefault(model_name, []).append("<model not diffed against a schema>")
            continue
        used = _ALLOW_USAGE.get(model_name, set())
        for alias in aliases:
            if alias not in used:
                out.setdefault(model_name, []).append(alias)
    return out


def invalid_mapping_entries(schemas: Dict[str, dict]) -> Dict[str, List[str]]:
    """Alias/exempt entries that reference a missing schema or a missing model."""
    known = {m.__name__ for m in _resource_models()}
    out: Dict[str, List[str]] = {}
    for name, schema in SCHEMA_ALIASES.items():
        if name not in known:
            out.setdefault("SCHEMA_ALIASES", []).append(f"{name} (no such model)")
        elif schema not in schemas:
            out.setdefault("SCHEMA_ALIASES", []).append(f"{name} -> {schema} (no such schema)")
    for name in EXEMPT_MODELS:
        if name not in known:
            out.setdefault("EXEMPT_MODELS", []).append(f"{name} (no such model)")
    return out


# --------------------------------------------------------------------------- #
# Rendering
# --------------------------------------------------------------------------- #
def render_summary_markdown(schemas: Dict[str, dict]) -> str:
    """Human summary for the weekly drift issue (never raises; informational)."""
    drifts = all_drift(schemas)
    failing = [d for d in drifts if d.has_failures]
    lines: List[str] = []
    if not failing:
        lines.append("_No model/spec field drift: every model matches its schema "
                     "(or an allowlisted, live-verified divergence)._")
    else:
        lines.append("| Model | Schema | Drift |")
        lines.append("|---|---|---|")
        for d in failing:
            bits: List[str] = []
            if d.model_only:
                bits.append("model-only: " + ", ".join(f"`{a}`" for a in d.model_only))
            if d.type_mismatch:
                bits.append(
                    "type: "
                    + ", ".join(f"`{a}` ({m}≠{s})" for a, m, s in d.type_mismatch)
                )
            if d.missing_required:
                bits.append("missing required: " + ", ".join(f"`{a}`" for a in d.missing_required))
            lines.append(f"| `{d.model_name}` | `{d.schema}` | {'; '.join(bits)} |")
    optional = [(d.model_name, d.missing_optional) for d in drifts if d.missing_optional]
    if optional:
        lines.append("")
        lines.append("<details><summary>Unmodelled optional spec fields "
                     "(informational — tolerated by <code>extra=\"allow\"</code>)</summary>")
        lines.append("")
        for model_name, fields in sorted(optional):
            lines.append(f"- `{model_name}`: " + ", ".join(f"`{f}`" for f in sorted(fields)))
        lines.append("")
        lines.append("</details>")
    return "\n".join(lines) + "\n"


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument(
        "--summary",
        metavar="SPEC",
        help="print the model/spec drift summary (markdown) for the given OpenAPI "
        "JSON file and exit 0 (informational; used by the weekly drift workflow)",
    )
    args = parser.parse_args(argv)

    if args.summary:
        schemas = load_schemas(Path(args.summary))
        sys.stdout.write(render_summary_markdown(schemas))
        return 0

    # Default: enforce against the committed snapshot (handy locally; the unit
    # test asserts the same conditions on every CI run).
    schemas = load_schemas(UPSTREAM_SPEC)
    failed = False
    unresolved = unresolved_models(schemas)
    if unresolved:
        failed = True
        print(f"Unresolved models (add a SCHEMA_ALIASES or EXEMPT_MODELS entry): {unresolved}",
              file=sys.stderr)
    invalid = invalid_mapping_entries(schemas)
    if invalid:
        failed = True
        print(f"Invalid mapping entries: {invalid}", file=sys.stderr)
    stale = stale_allowlist_entries(schemas)
    if stale:
        failed = True
        print(f"Stale ALLOWED_DIVERGENCES entries (suppress nothing): {stale}", file=sys.stderr)
    for d in all_drift(schemas):
        if d.has_failures:
            failed = True
            print(f"{d.model_name} -> {d.schema}: model_only={d.model_only} "
                  f"type_mismatch={d.type_mismatch} missing_required={d.missing_required}",
                  file=sys.stderr)
    if failed:
        return 1
    print("All resource models match their OpenAPI schema (or an allowlisted divergence).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
