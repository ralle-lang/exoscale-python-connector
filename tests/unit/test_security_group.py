"""Unit tests for the SecurityGroupClient (reference asset-type tests)."""
from __future__ import annotations

import responses

from exoscale_connector.resources.security_group import (
    SecurityGroupClient,
    SecurityGroupResource,
    SecurityGroupRule,
)


@responses.activate
def test_list_parses_typed_models(client, base_url) -> None:
    responses.add(
        responses.GET,
        f"{base_url}/security-group",
        json={"security-groups": [{"id": "sg1", "name": "web"}, {"id": "sg2", "name": "db"}]},
        status=200,
    )
    groups = SecurityGroupClient(client).list()
    assert [g.name for g in groups] == ["web", "db"]


@responses.activate
def test_find_by_name(client, base_url) -> None:
    responses.add(
        responses.GET,
        f"{base_url}/security-group",
        json={"security-groups": [{"id": "sg1", "name": "web"}]},
        status=200,
    )
    found = SecurityGroupClient(client).find_by_name("WEB")
    assert found is not None and found.id == "sg1"


@responses.activate
def test_create_awaits_operation_and_refetches(client, base_url) -> None:
    # POST returns an async operation referencing the new resource...
    responses.add(
        responses.POST,
        f"{base_url}/security-group",
        json={"id": "op1", "state": "success", "reference": {"id": "sg-new"}},
        status=200,
    )
    # ...which the client re-fetches once the operation settles.
    responses.add(
        responses.GET,
        f"{base_url}/security-group/sg-new",
        json={"id": "sg-new", "name": "api"},
        status=200,
    )
    created = SecurityGroupClient(client).create({"name": "api"})
    assert created.id == "sg-new"
    assert created.name == "api"


@responses.activate
def test_delete_returns_settled_operation(client, base_url) -> None:
    responses.add(
        responses.DELETE,
        f"{base_url}/security-group/sg1",
        json={"id": "op9", "state": "pending"},
        status=200,
    )
    responses.add(
        responses.GET,
        f"{base_url}/operation/op9",
        json={"id": "op9", "state": "success"},
        status=200,
    )
    op = SecurityGroupClient(client).delete("sg1")
    assert op.state == "success"


@responses.activate
def test_add_rule_posts_kebab_payload(client, base_url) -> None:
    responses.add(
        responses.POST,
        f"{base_url}/security-group/sg1/rules",
        json={"id": "op2", "state": "success"},
        status=200,
    )
    rule = SecurityGroupRule(
        flow_direction="ingress", protocol="tcp", start_port=443, end_port=443, network="0.0.0.0/0"
    )
    SecurityGroupClient(client).add_rule("sg1", rule)
    sent = responses.calls[0].request.body
    assert b'"flow-direction": "ingress"' in sent
    assert b'"start-port": 443' in sent


@responses.activate
def test_rule_typed_public_security_group_reference(client, base_url) -> None:
    """A rule's security_group parses as a typed SecurityGroupResource, incl. visibility."""
    responses.add(
        responses.GET,
        f"{base_url}/security-group/sg1",
        json={
            "id": "sg1",
            "name": "web",
            "rules": [
                {
                    "id": "r1",
                    "flow-direction": "ingress",
                    "protocol": "tcp",
                    "security-group": {"id": "pub1", "name": "managed", "visibility": "public"},
                },
                {
                    "id": "r2",
                    "flow-direction": "ingress",
                    "protocol": "tcp",
                    "security-group": {"id": "peer1"},
                },
            ],
        },
        status=200,
    )
    group = SecurityGroupClient(client).get("sg1")
    public_rule, private_rule = group.rules
    assert isinstance(public_rule.security_group, SecurityGroupResource)
    assert public_rule.security_group.visibility == "public"
    assert public_rule.security_group.id == "pub1"
    # A bare id-only reference still parses; visibility is simply absent.
    assert private_rule.security_group.id == "peer1"
    assert private_rule.security_group.visibility is None


def test_public_security_group_rule_serialises_visibility() -> None:
    """A public-SG rule round-trips visibility on the outbound payload (kebab-case)."""
    rule = SecurityGroupRule(
        flow_direction="ingress",
        protocol="tcp",
        security_group=SecurityGroupResource(id="pub1", visibility="public"),
    )
    payload = rule.to_api_payload()
    assert payload["security-group"] == {"id": "pub1", "visibility": "public"}
    assert payload["flow-direction"] == "ingress"
