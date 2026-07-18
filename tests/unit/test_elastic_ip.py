"""Unit tests for ElasticIPClient."""

from __future__ import annotations

import responses

from exoscale_connector.resources.elastic_ip import ElasticIP, ElasticIPClient


@responses.activate
def test_list_parses_typed_models(client, base_url) -> None:
    responses.add(
        responses.GET,
        f"{base_url}/elastic-ip",
        json={
            "elastic-ips": [
                {"id": "eip1", "ip": "1.2.3.4"},
                {"id": "eip2", "ip": "5.6.7.8"},
            ]
        },
        status=200,
    )
    eips = ElasticIPClient(client).list()
    assert [e.id for e in eips] == ["eip1", "eip2"]
    assert eips[0].ip == "1.2.3.4"


@responses.activate
def test_get_returns_model(client, base_url) -> None:
    responses.add(
        responses.GET,
        f"{base_url}/elastic-ip/eip1",
        json={"id": "eip1", "ip": "1.2.3.4", "description": "my eip"},
        status=200,
    )
    eip = ElasticIPClient(client).get("eip1")
    assert isinstance(eip, ElasticIP)
    assert eip.description == "my eip"


@responses.activate
def test_find_by_name_matches_on_ip_field(client, base_url) -> None:
    # ElasticIPs have no 'name' field; find_by_name falls through gracefully
    # (returns None when no attribute matches).
    responses.add(
        responses.GET,
        f"{base_url}/elastic-ip",
        json={"elastic-ips": [{"id": "eip1", "ip": "1.2.3.4"}]},
        status=200,
    )
    # name_field defaults to "name"; ElasticIP has no name, so no match.
    found = ElasticIPClient(client).find_by_name("1.2.3.4")
    assert found is None


@responses.activate
def test_create_awaits_operation_and_refetches(client, base_url) -> None:
    responses.add(
        responses.POST,
        f"{base_url}/elastic-ip",
        json={"id": "op1", "state": "success", "reference": {"id": "eip-new"}},
        status=200,
    )
    responses.add(
        responses.GET,
        f"{base_url}/elastic-ip/eip-new",
        json={"id": "eip-new", "ip": "9.9.9.9"},
        status=200,
    )
    created = ElasticIPClient(client).create({"description": "test"})
    assert created.id == "eip-new"
    assert created.ip == "9.9.9.9"


@responses.activate
def test_delete_returns_settled_operation(client, base_url) -> None:
    responses.add(
        responses.DELETE,
        f"{base_url}/elastic-ip/eip1",
        json={"id": "op9", "state": "pending"},
        status=200,
    )
    responses.add(
        responses.GET,
        f"{base_url}/operation/op9",
        json={"id": "op9", "state": "success"},
        status=200,
    )
    op = ElasticIPClient(client).delete("eip1")
    assert op.state == "success"


@responses.activate
def test_healthcheck_nested_model_parses(client, base_url) -> None:
    """Healthcheck nested object should be deserialised into ElasticIPHealthcheck."""
    responses.add(
        responses.GET,
        f"{base_url}/elastic-ip/eip1",
        json={
            "id": "eip1",
            "ip": "1.2.3.4",
            "healthcheck": {
                "mode": "https",
                "port": 443,
                "uri": "/health",
                "interval": 10,
                "timeout": 5,
                "strikes-ok": 2,
                "strikes-fail": 3,
            },
        },
        status=200,
    )
    eip = ElasticIPClient(client).get("eip1")
    assert eip.healthcheck is not None
    assert eip.healthcheck.mode == "https"
    assert eip.healthcheck.port == 443
    # kebab-case aliases must round-trip to snake_case attributes
    assert eip.healthcheck.strikes_ok == 2
    assert eip.healthcheck.strikes_fail == 3


@responses.activate
def test_labels_field_parses(client, base_url) -> None:
    responses.add(
        responses.GET,
        f"{base_url}/elastic-ip/eip1",
        json={"id": "eip1", "ip": "1.2.3.4", "labels": {"env": "prod", "team": "ops"}},
        status=200,
    )
    eip = ElasticIPClient(client).get("eip1")
    assert eip.labels == {"env": "prod", "team": "ops"}
