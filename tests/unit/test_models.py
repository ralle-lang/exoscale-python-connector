"""Unit tests for the pydantic model infrastructure (kebab-case aliasing)."""
from __future__ import annotations

from exoscale_connector.models import Operation, to_api_payload
from exoscale_connector.resources.security_group import SecurityGroupRule


def test_snake_case_attributes_map_to_kebab_aliases() -> None:
    rule = SecurityGroupRule(flow_direction="ingress", start_port=443, end_port=443, protocol="tcp")
    payload = rule.to_api_payload()
    assert payload == {
        "flow-direction": "ingress",
        "start-port": 443,
        "end-port": 443,
        "protocol": "tcp",
    }


def test_parse_kebab_response_into_snake_attributes() -> None:
    rule = SecurityGroupRule.model_validate(
        {"flow-direction": "egress", "start-port": 53, "protocol": "udp"}
    )
    assert rule.flow_direction == "egress"
    assert rule.start_port == 53


def test_operation_reference_id_accessor() -> None:
    op = Operation.model_validate(
        {"id": "op-1", "state": "success", "reference": {"id": "res-9"}}
    )
    assert op.reference_id == "res-9"


def test_to_api_payload_accepts_dict_and_drops_none() -> None:
    assert to_api_payload({"a": 1, "b": None}) == {"a": 1}
    assert to_api_payload(None) is None


def test_unknown_fields_are_preserved() -> None:
    rule = SecurityGroupRule.model_validate({"id": "r1", "brand-new-field": "x"})
    dumped = rule.model_dump(by_alias=True, exclude_none=True)
    assert dumped["brand-new-field"] == "x"
