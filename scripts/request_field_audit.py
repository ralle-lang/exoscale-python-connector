#!/usr/bin/env python3
"""Request-body coverage audit: spec request fields the connector cannot send.

The drift watch reports only what *changes* upstream, and the model gate
(``model_schema_drift.py``) compares *response* models. Neither notices a
request field that has always been in the spec but that a client method never
sends — e.g. the optional ``ipv4`` on the VPC subnet attach endpoint, which went
unnoticed until a user asked for it. This audit closes that gap (decision D5).

For every APIv2 operation on a path the connector reaches, it finds the
client methods that call that exact verb + path (via
:mod:`ast`, the same discovery as ``drift_operations.py``) and classifies them:

- ``no-method`` — the path family is covered, but nothing calls this verb/path
  (e.g. a colon action with no client method), body or not;
- ``missing`` — every calling method builds a fixed body (dict literal, or a
  named dict filled key by key) that lacks some spec properties;
- passthrough — a method forwards a caller-supplied payload
  (``to_api_payload(...)`` or any other non-literal), so every field is already
  sendable. Not reported as a gap.

Only top-level body properties are compared. Intentional omissions go in
:data:`KNOWN_OMISSIONS` (fields) or :data:`KNOWN_UNCALLED` (operations) with a
reason so the report stays a list of real gaps.

Informational, not a gate: run it at release boundaries, curate the findings,
and route them through the roadmap like additive drift.
"""

from __future__ import annotations

import argparse
import ast
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import drift_operations as ops  # noqa: E402

DEFAULT_SPEC = ops.REPO_ROOT / ".github" / "upstream" / "openapi-v2.json"
VERBS = {"get", "post", "put", "delete"}

# (METHOD, normalised spec path) -> {field: reason}. Fields deliberately not sent.
KNOWN_OMISSIONS: dict[tuple[str, str], dict[str, str]] = {}

# (METHOD, normalised spec path) -> reason. Operations deliberately left without
# a method, usually because an equivalent endpoint already does the job.
KNOWN_UNCALLED: dict[tuple[str, str], str] = {
    **{
        (
            "DELETE",
            f"dbaas-{engine}/{{}}",
        ): "deleted through the generic DELETE /dbaas-service/{name}"
        for engine in (
            "clickhouse",
            "grafana",
            "kafka",
            "mysql",
            "opensearch",
            "postgres",
            "thanos",
            "valkey",
        )
    },
}


@dataclass(frozen=True)
class ClientCall:
    """One ``self.client.<verb>(endpoint, json=...)`` call inside a method."""

    module: str
    method: str
    verb: str
    endpoint: str
    # Top-level body keys the call can send; ``None`` means passthrough.
    fields: frozenset[str] | None


@dataclass
class Finding:
    verb: str
    path: str
    operation_id: str
    kind: str  # "no-method" | "missing"
    missing: list[str] = field(default_factory=list)
    callers: list[str] = field(default_factory=list)


# --------------------------------------------------------------------------- #
# Code side
# --------------------------------------------------------------------------- #
def _dict_keys(node: ast.AST) -> set[str] | None:
    """String keys of a dict literal (or both arms of a conditional), else ``None``."""
    if isinstance(node, ast.Dict):
        keys: set[str] = set()
        for key in node.keys:
            if isinstance(key, ast.Constant) and isinstance(key.value, str):
                keys.add(key.value)
            else:  # ``**spread`` or a computed key: cannot enumerate
                return None
        return keys
    if isinstance(node, ast.IfExp):
        branches = [_dict_keys(node.body), _dict_keys(node.orelse)]
        if any(
            b is None and not _is_none(arm)
            for b, arm in zip(branches, (node.body, node.orelse), strict=True)
        ):
            return None
        return set().union(*(b for b in branches if b is not None))
    if _is_none(node):
        return set()
    return None


def _is_none(node: ast.AST) -> bool:
    return isinstance(node, ast.Constant) and node.value is None


class _MethodCalls(ast.NodeVisitor):
    def __init__(self, module: str, collection_path: str) -> None:
        self.module = module
        self.renderer = ops._EndpointVisitor([collection_path] if collection_path else [])
        self.calls: list[ClientCall] = []

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        # Endpoint locals (``path = f"..."``) for the renderer.
        self.renderer._locals = {}
        bodies: dict[str, set[str] | None] = {}
        for stmt in ast.walk(node):
            if isinstance(stmt, ast.Assign) and len(stmt.targets) == 1:
                target = stmt.targets[0]
                if isinstance(target, ast.Name):
                    rendered = self.renderer._render(stmt.value)
                    if rendered is not None:
                        self.renderer._locals[target.id] = rendered
                    bodies[target.id] = _dict_keys(stmt.value)
                elif (
                    isinstance(target, ast.Subscript)
                    and isinstance(target.value, ast.Name)
                    and isinstance(target.slice, ast.Constant)
                    and isinstance(target.slice.value, str)
                ):
                    known = bodies.get(target.value.id)
                    if known is not None:
                        known.add(target.slice.value)
            elif (
                isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name) and stmt.value
            ):
                bodies[stmt.target.id] = _dict_keys(stmt.value)
        for call in ast.walk(node):
            if not (
                isinstance(call, ast.Call)
                and isinstance(call.func, ast.Attribute)
                and call.func.attr in VERBS
                and isinstance(call.func.value, ast.Attribute)
                and call.func.value.attr == "client"
                and call.args
            ):
                continue
            endpoint = self.renderer._render(call.args[0])
            if endpoint is None:
                continue
            body = next((kw.value for kw in call.keywords if kw.arg == "json"), None)
            fields: set[str] | None
            if body is None:
                fields = set()
            elif isinstance(body, ast.Name):
                fields = bodies.get(body.id)
            else:
                fields = _dict_keys(body)
            self.calls.append(
                ClientCall(
                    module=self.module,
                    method=node.name,
                    verb=call.func.attr.upper(),
                    endpoint=endpoint,
                    fields=None if fields is None else frozenset(fields),
                )
            )


def calls_in_source(source: str, module: str, collection_path: str = "") -> list[ClientCall]:
    """Every client call in ``source``, with ``self.collection_path`` resolved."""
    visitor = _MethodCalls(module, collection_path)
    visitor.visit(ast.parse(source))
    return visitor.calls


def discovered_calls() -> list[ClientCall]:
    """Client calls across all resource modules, base-class verbs included.

    ``_base.py`` is rendered once per concrete client so the generic
    ``create``/``update``/``delete`` count for every collection path; mixins
    (``_reverse_dns.py``) are scanned with their own literal paths.
    """
    collection_paths = ops._module_collection_paths()
    calls: list[ClientCall] = []
    base_source = (ops.RESOURCES_DIR / "_base.py").read_text(encoding="utf-8")
    for path in sorted(ops.RESOURCES_DIR.glob("*.py")):
        stem = path.stem
        if stem in {"__init__", "_base"}:
            continue
        source = path.read_text(encoding="utf-8")
        own = collection_paths.get(stem, [""])
        calls += calls_in_source(source, stem, own[0])
        for cp in collection_paths.get(stem, []):
            calls += calls_in_source(base_source, stem, cp)
    return calls


# --------------------------------------------------------------------------- #
# Spec side
# --------------------------------------------------------------------------- #
def _segment_regex(segment: str) -> re.Pattern[str]:
    # A rendered ``{}`` is a runtime value: it fills a spec ``{param}`` or a
    # literal (``dbaas-{}`` -> ``dbaas-postgres``) but never swallows a colon
    # action (``{}`` must not match ``{}:start``).
    return re.compile(
        "".join("[^:/]+" if p == "{}" else re.escape(p) for p in re.split(r"(\{\})", segment))
    )


def endpoint_matches(endpoint: str, spec_path: str) -> bool:
    """Exact (same depth) match of a rendered endpoint against a spec path."""
    e_segs = ops._segments(endpoint)
    p_segs = ops._segments(spec_path)
    return len(e_segs) == len(p_segs) and all(
        _segment_regex(e).fullmatch(p) for e, p in zip(e_segs, p_segs, strict=True)
    )


def _request_properties(spec: dict, operation: dict) -> dict | None:
    body = operation.get("requestBody")
    if not body:
        return None
    schema = body.get("content", {}).get("application/json", {}).get("schema", {})
    ref = schema.get("$ref")
    if ref:
        schema = spec.get("components", {}).get("schemas", {}).get(ref.rsplit("/", 1)[-1], {})
    return schema.get("properties") or {}


def _in_scope(spec_path: str) -> bool:
    collection_paths = ops._module_collection_paths()
    for stem, own in collection_paths.items():
        templates = list(own) + list(ops.MODULE_SIBLING_OPERATIONS.get(stem, []))
        if any(ops.template_covers(t, spec_path) for t in templates):
            return True
    return ops.template_covers("reverse-dns", spec_path)


def audit(spec: dict, calls: list[ClientCall] | None = None) -> list[Finding]:
    calls = discovered_calls() if calls is None else calls
    findings: list[Finding] = []
    for raw_path, item in sorted(spec.get("paths", {}).items()):
        path = ops._normalize(raw_path)
        if not _in_scope(path):
            continue
        for verb, operation in sorted(item.items()):
            if not isinstance(operation, dict) or verb not in VERBS:
                continue
            props = _request_properties(spec, operation)
            verb_u = verb.upper()
            hits = [c for c in calls if c.verb == verb_u and endpoint_matches(c.endpoint, path)]
            op_id = operation.get("operationId", "")
            if not hits:
                if (verb_u, path) not in KNOWN_UNCALLED:
                    findings.append(Finding(verb_u, path, op_id, "no-method"))
                continue
            if props is None:
                continue
            if any(c.fields is None for c in hits):
                continue  # passthrough: every field is sendable
            sent = set().union(*(c.fields or set() for c in hits))
            omitted = KNOWN_OMISSIONS.get((verb_u, path), {})
            missing = sorted(k for k in props if k not in sent and k not in omitted)
            if missing:
                callers = sorted({f"{c.module}.{c.method}" for c in hits})
                findings.append(Finding(verb_u, path, op_id, "missing", missing, callers))
    return findings


def render_markdown(findings: list[Finding]) -> str:
    if not findings:
        return "_No request-body gaps: every in-scope operation can send all its fields._\n"
    lines = ["| Operation | Gap | Detail |", "|---|---|---|"]
    for f in findings:
        op = f"`{f.verb} /{f.path}` ({f.operation_id})"
        if f.kind == "no-method":
            lines.append(f"| {op} | no method | path family is covered, this verb/path is not |")
        else:
            detail = f"{', '.join(f'`{m}`' for m in f.missing)} — via {', '.join(f.callers)}"
            lines.append(f"| {op} | missing fields | {detail} |")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    import json

    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("spec", nargs="?", default=str(DEFAULT_SPEC), help="OpenAPI JSON")
    args = parser.parse_args(argv)
    spec = json.loads(Path(args.spec).read_text(encoding="utf-8"))
    sys.stdout.write(render_markdown(audit(spec)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
