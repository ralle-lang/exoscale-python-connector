"""Unit tests for IAMRoleClient."""

from __future__ import annotations

import json

import responses

from exoscale_connector.resources.iam_role import (
    IAMPolicy,
    IAMPolicyRule,
    IAMPolicyService,
    IAMRole,
    IAMRoleClient,
    RuleAction,
    ServiceStrategy,
    ServiceType,
)


@responses.activate
def test_list_parses_typed_models(client, base_url) -> None:
    responses.add(
        responses.GET,
        f"{base_url}/iam-role",
        json={
            "iam-roles": [
                {"id": "role-1", "name": "read-only"},
                {"id": "role-2", "name": "admin"},
            ]
        },
        status=200,
    )
    roles = IAMRoleClient(client).list()
    assert [r.name for r in roles] == ["read-only", "admin"]


@responses.activate
def test_find_by_name(client, base_url) -> None:
    responses.add(
        responses.GET,
        f"{base_url}/iam-role",
        json={"iam-roles": [{"id": "role-1", "name": "read-only"}]},
        status=200,
    )
    found = IAMRoleClient(client).find_by_name("READ-ONLY")
    assert found is not None
    assert found.id == "role-1"


@responses.activate
def test_find_by_name_missing_returns_none(client, base_url) -> None:
    responses.add(
        responses.GET,
        f"{base_url}/iam-role",
        json={"iam-roles": []},
        status=200,
    )
    assert IAMRoleClient(client).find_by_name("ghost") is None


@responses.activate
def test_get_by_id(client, base_url) -> None:
    responses.add(
        responses.GET,
        f"{base_url}/iam-role/role-1",
        json={
            "id": "role-1",
            "name": "read-only",
            "editable": True,
            "permissions": ["compute-read"],
        },
        status=200,
    )
    role = IAMRoleClient(client).get("role-1")
    assert isinstance(role, IAMRole)
    assert role.permissions == ["compute-read"]
    assert role.editable is True


@responses.activate
def test_create_awaits_operation_and_refetches(client, base_url) -> None:
    responses.add(
        responses.POST,
        f"{base_url}/iam-role",
        json={"id": "op1", "state": "success", "reference": {"id": "role-new"}},
        status=200,
    )
    responses.add(
        responses.GET,
        f"{base_url}/iam-role/role-new",
        json={"id": "role-new", "name": "deployer"},
        status=200,
    )
    created = IAMRoleClient(client).create({"name": "deployer"})
    assert created.id == "role-new"
    assert created.name == "deployer"


@responses.activate
def test_update_awaits_operation_and_refetches(client, base_url) -> None:
    responses.add(
        responses.PUT,
        f"{base_url}/iam-role/role-1",
        json={"id": "op2", "state": "success", "reference": {"id": "role-1"}},
        status=200,
    )
    responses.add(
        responses.GET,
        f"{base_url}/iam-role/role-1",
        json={"id": "role-1", "name": "deployer-updated"},
        status=200,
    )
    updated = IAMRoleClient(client).update("role-1", {"description": "updated"})
    assert updated.name == "deployer-updated"


@responses.activate
def test_delete_returns_settled_operation(client, base_url) -> None:
    responses.add(
        responses.DELETE,
        f"{base_url}/iam-role/role-1",
        json={"id": "op9", "state": "pending"},
        status=200,
    )
    responses.add(
        responses.GET,
        f"{base_url}/operation/op9",
        json={"id": "op9", "state": "success"},
        status=200,
    )
    op = IAMRoleClient(client).delete("role-1")
    assert op.state == "success"


@responses.activate
def test_policy_nested_model_parsed(client, base_url) -> None:
    responses.add(
        responses.GET,
        f"{base_url}/iam-role/role-1",
        json={
            "id": "role-1",
            "name": "read-only",
            "policy": {"default-service-strategy": "deny", "services": {}},
        },
        status=200,
    )
    role = IAMRoleClient(client).get("role-1")
    assert role.policy is not None
    assert role.policy.default_service_strategy == "deny"


@responses.activate
def test_policy_rules_form_parsed(client, base_url) -> None:
    # A real "rules" form: a deny-then-allow rule list on one service plus a
    # blanket-allow on another (shapes taken from the live console examples).
    responses.add(
        responses.GET,
        f"{base_url}/iam-role/role-2",
        json={
            "id": "role-2",
            "name": "sos-backup",
            "policy": {
                "default-service-strategy": "deny",
                "services": {
                    "sos": {
                        "type": "rules",
                        "rules": [
                            {"action": "deny", "expression": 'resources.bucket != "backups"'},
                            {"action": "allow", "expression": "true"},
                        ],
                    },
                    "compute": {"type": "allow"},
                },
            },
        },
        status=200,
    )
    pol = IAMRoleClient(client).get("role-2").policy
    assert pol is not None
    assert pol.default_service_strategy == "deny"
    sos = pol.services["sos"]
    assert isinstance(sos, IAMPolicyService)
    assert sos.type == "rules"
    assert [r.action for r in sos.rules] == ["deny", "allow"]
    assert sos.rules[0].expression == 'resources.bucket != "backups"'
    # Blanket-allow service carries no rule list.
    assert pol.services["compute"].type == "allow"
    assert pol.services["compute"].rules is None


def test_policy_round_trips_to_kebab_wire_payload() -> None:
    # Building a policy in Python serialises to the exact wire shape the API
    # expects: kebab top-level key, open services map, and per-rule fields.
    policy = IAMPolicy(
        default_service_strategy="deny",
        services={
            "dns": IAMPolicyService(
                type="rules",
                rules=[
                    IAMPolicyRule(action="deny", expression="parameters.type != 'TXT'"),
                    IAMPolicyRule(action="allow", expression="true", resources=["dns_domain"]),
                ],
            ),
        },
    )
    assert policy.to_api_payload() == {
        "default-service-strategy": "deny",
        "services": {
            "dns": {
                "type": "rules",
                "rules": [
                    {"action": "deny", "expression": "parameters.type != 'TXT'"},
                    {"action": "allow", "expression": "true", "resources": ["dns_domain"]},
                ],
            },
        },
    }


@responses.activate
def test_assume_role_policy_parsed(client, base_url) -> None:
    responses.add(
        responses.GET,
        f"{base_url}/iam-role/role-1",
        json={
            "id": "role-1",
            "name": "assumable",
            "assume-role-policy": {"default-service-strategy": "allow", "services": {}},
        },
        status=200,
    )
    role = IAMRoleClient(client).get("role-1")
    assert role.assume_role_policy is not None
    assert role.assume_role_policy.default_service_strategy == "allow"


@responses.activate
def test_set_policy_puts_to_subendpoint(client, base_url) -> None:
    responses.add(
        responses.PUT,
        f"{base_url}/iam-role/role-1:policy",
        json={"id": "op1", "state": "success"},
        status=200,
    )
    op = IAMRoleClient(client).set_policy("role-1", IAMPolicy.allow_services(["dns"]))
    assert op.state == "success"
    assert len(responses.calls) == 1  # settled inline; no extra poll
    sent = json.loads(responses.calls[0].request.body)
    assert sent == {"default-service-strategy": "deny", "services": {"dns": {"type": "allow"}}}


@responses.activate
def test_set_assume_role_policy_puts_to_generic_update(client, base_url) -> None:
    # No :assume-role-policy sub-endpoint exists (404s live); the policy goes
    # nested under "assume-role-policy" in the generic PUT /iam-role/{id} body.
    responses.add(
        responses.PUT,
        f"{base_url}/iam-role/role-1",
        json={"id": "op2", "state": "success"},
        status=200,
    )
    op = IAMRoleClient(client).set_assume_role_policy(
        "role-1", {"default-service-strategy": "deny"}
    )
    assert op.state == "success"
    sent = json.loads(responses.calls[0].request.body)
    assert sent == {"assume-role-policy": {"default-service-strategy": "deny"}}


def test_policy_preserves_unknown_fields() -> None:
    # extra="allow" keeps fields the connector does not model, at every level,
    # so the library survives the API gaining new policy attributes.
    pol = IAMPolicy.model_validate(
        {
            "default-service-strategy": "allow",
            "services": {"compute": {"type": "allow", "future-field": 42}},
            "future-top": "x",
        }
    )
    dumped = pol.to_api_payload()
    assert dumped["future-top"] == "x"
    assert dumped["services"]["compute"]["future-field"] == 42


def test_policy_factory_deny_all_and_allow_all() -> None:
    assert IAMPolicy.deny_all().to_api_payload() == {
        "default-service-strategy": "deny",
        "services": {},
    }
    assert IAMPolicy.allow_all().to_api_payload() == {
        "default-service-strategy": "allow",
        "services": {},
    }


def test_policy_factory_allow_services() -> None:
    pol = IAMPolicy.allow_services(["compute", "dns"])
    assert pol.to_api_payload() == {
        "default-service-strategy": "deny",
        "services": {
            "compute": {"type": "allow"},
            "dns": {"type": "allow"},
        },
    }


def test_service_and_rule_factories_build_rules_form() -> None:
    svc = IAMPolicyService.with_rules(
        IAMPolicyRule.deny("resources.bucket != 'backups'"),
        IAMPolicyRule.allow("true", resources=["sos_bucket"]),
    )
    assert svc.type == "rules"
    assert [r.action for r in svc.rules] == ["deny", "allow"]
    assert svc.to_api_payload() == {
        "type": "rules",
        "rules": [
            {"action": "deny", "expression": "resources.bucket != 'backups'"},
            {"action": "allow", "expression": "true", "resources": ["sos_bucket"]},
        ],
    }
    assert IAMPolicyService.allow().to_api_payload() == {"type": "allow"}
    assert IAMPolicyService.deny().to_api_payload() == {"type": "deny"}


def test_enum_constants_serialize_as_plain_strings() -> None:
    # Enum members are interchangeable with their string value and survive the
    # round-trip as plain strings, so they never change the wire payload.
    rule = IAMPolicyRule(action=RuleAction.ALLOW, expression="true")
    assert rule.action == "allow"
    assert rule.to_api_payload() == {"action": "allow", "expression": "true"}
    assert ServiceType.RULES == "rules"
    assert ServiceStrategy.DENY == "deny"
