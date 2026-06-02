"""Unit tests for AntiAffinityGroupClient."""
from __future__ import annotations

import responses

from exoscale_connector.resources.anti_affinity_group import AntiAffinityGroupClient


@responses.activate
def test_list_parses_typed_models(client, base_url) -> None:
    responses.add(
        responses.GET,
        f"{base_url}/anti-affinity-group",
        json={
            "anti-affinity-groups": [
                {"id": "aag-1", "name": "web-tier"},
                {"id": "aag-2", "name": "db-tier"},
            ]
        },
        status=200,
    )
    groups = AntiAffinityGroupClient(client).list()
    assert [g.name for g in groups] == ["web-tier", "db-tier"]


@responses.activate
def test_get_includes_instance_references(client, base_url) -> None:
    responses.add(
        responses.GET,
        f"{base_url}/anti-affinity-group/aag-1",
        json={
            "id": "aag-1",
            "name": "web-tier",
            "description": "Keep web nodes on separate hosts",
            "instances": [{"id": "i-a"}, {"id": "i-b"}],
        },
        status=200,
    )
    group = AntiAffinityGroupClient(client).get("aag-1")
    assert group.id == "aag-1"
    assert group.description == "Keep web nodes on separate hosts"
    assert len(group.instances) == 2
    assert group.instances[0].id == "i-a"


@responses.activate
def test_find_by_name_case_insensitive(client, base_url) -> None:
    responses.add(
        responses.GET,
        f"{base_url}/anti-affinity-group",
        json={"anti-affinity-groups": [{"id": "aag-1", "name": "web-tier"}]},
        status=200,
    )
    found = AntiAffinityGroupClient(client).find_by_name("WEB-TIER")
    assert found is not None and found.id == "aag-1"


@responses.activate
def test_find_by_name_returns_none_when_absent(client, base_url) -> None:
    responses.add(
        responses.GET,
        f"{base_url}/anti-affinity-group",
        json={"anti-affinity-groups": [{"id": "aag-1", "name": "web-tier"}]},
        status=200,
    )
    assert AntiAffinityGroupClient(client).find_by_name("nonexistent") is None


@responses.activate
def test_create_awaits_operation_and_refetches(client, base_url) -> None:
    responses.add(
        responses.POST,
        f"{base_url}/anti-affinity-group",
        json={"id": "op1", "state": "success", "reference": {"id": "aag-new"}},
        status=200,
    )
    responses.add(
        responses.GET,
        f"{base_url}/anti-affinity-group/aag-new",
        json={"id": "aag-new", "name": "app-tier"},
        status=200,
    )
    group = AntiAffinityGroupClient(client).create({"name": "app-tier"})
    assert group.id == "aag-new"
    assert group.name == "app-tier"


@responses.activate
def test_delete_returns_settled_operation(client, base_url) -> None:
    responses.add(
        responses.DELETE,
        f"{base_url}/anti-affinity-group/aag-1",
        json={"id": "op9", "state": "pending"},
        status=200,
    )
    responses.add(
        responses.GET,
        f"{base_url}/operation/op9",
        json={"id": "op9", "state": "success"},
        status=200,
    )
    op = AntiAffinityGroupClient(client).delete("aag-1")
    assert op.state == "success"
