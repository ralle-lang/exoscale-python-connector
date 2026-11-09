"""Tests for the request-body coverage audit (``scripts/request_field_audit.py``)."""

from __future__ import annotations

import json

from scripts.drift_operations import _normalize
from scripts.request_field_audit import (
    DEFAULT_SPEC,
    KNOWN_OMISSIONS,
    KNOWN_UNCALLED,
    ClientCall,
    audit,
    calls_in_source,
    endpoint_matches,
    render_markdown,
)

SOURCE = """
class Thing:
    def literal(self, tid):
        return self.client.put(f"{self.collection_path}/{tid}:attach", json={"instance": {}})

    def built(self, tid, ip=None):
        body: dict = {"instance": {}}
        if ip is not None:
            body["ipv4"] = ip
        return self.client.put(f"{self.collection_path}/{tid}:pin", json=body)

    def conditional(self, tid, profile=None):
        body = {"rescue-profile": profile} if profile else None
        return self.client.put(f"{self.collection_path}/{tid}:start", json=body)

    def forwarded(self, payload):
        return self.client.post(self.collection_path, json=to_api_payload(payload))

    def bare(self, tid):
        return self.client.put(f"{self.collection_path}/{tid}:stop")
"""


def _by_method(calls: list[ClientCall]) -> dict[str, ClientCall]:
    return {c.method: c for c in calls}


def test_body_shapes_are_classified():
    calls = _by_method(calls_in_source(SOURCE, "thing", "thing"))
    assert calls["literal"].endpoint == "thing/{}:attach"
    assert calls["literal"].fields == {"instance"}
    assert calls["built"].fields == {"instance", "ipv4"}
    assert calls["conditional"].fields == {"rescue-profile"}
    assert calls["forwarded"].fields is None  # passthrough
    assert calls["bare"].fields == frozenset()
    assert calls["forwarded"].verb == "POST"


def test_endpoint_matching_is_exact_and_colon_aware():
    assert endpoint_matches("instance/{}:start", "/instance/{id}:start")
    assert endpoint_matches("dbaas-{}/{}/user", "/dbaas-postgres/{name}/user")
    assert endpoint_matches("reverse-dns/{}/{}", "/reverse-dns/instance/{id}")
    # A runtime value never swallows a colon action, and depth must match.
    assert not endpoint_matches("instance/{}", "/instance/{id}:start")
    assert not endpoint_matches("sks-cluster/{}", "/sks-cluster/{id}/nodepool")


def _spec(paths: dict) -> dict:
    return {"paths": paths, "components": {"schemas": {}}}


def _body(*props: str) -> dict:
    schema = {"type": "object", "properties": {p: {"type": "string"} for p in props}}
    return {"requestBody": {"content": {"application/json": {"schema": schema}}}}


def test_audit_reports_missing_fields_and_missing_methods():
    calls = [
        ClientCall(
            "vpc", "attach_subnet", "PUT", "vpc/{}/subnet/{}/attach", frozenset({"instance"})
        ),
        ClientCall("vpc", "create", "POST", "vpc", None),
    ]
    spec = _spec(
        {
            "/vpc/{id}/subnet/{sid}/attach": {
                "put": {"operationId": "a", **_body("instance", "ipv4")}
            },
            "/vpc/{id}/subnet/{sid}/detach": {"put": {"operationId": "d", **_body("instance")}},
            "/vpc": {"post": {"operationId": "c", **_body("name", "anything")}},
        }
    )
    findings = {f.operation_id: f for f in audit(spec, calls)}
    assert findings["a"].kind == "missing" and findings["a"].missing == ["ipv4"]
    assert findings["d"].kind == "no-method"
    assert "c" not in findings  # passthrough covers every field
    assert "`ipv4`" in render_markdown(list(findings.values()))


def test_known_omissions_target_real_operations():
    """A stale omission entry would silently hide nothing; keep the list honest."""
    spec = json.loads(DEFAULT_SPEC.read_text(encoding="utf-8"))
    operations = {
        (verb.upper(), _normalize(path)) for path, item in spec["paths"].items() for verb in item
    }
    for key in [*KNOWN_OMISSIONS, *KNOWN_UNCALLED]:
        assert key in operations, f"{key} is not an operation in the spec snapshot"


def test_snapshot_audit_runs():
    spec = json.loads(DEFAULT_SPEC.read_text(encoding="utf-8"))
    assert isinstance(render_markdown(audit(spec)), str)
