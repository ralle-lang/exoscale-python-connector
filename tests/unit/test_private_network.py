"""Unit tests for PrivateNetworkClient."""

from __future__ import annotations

import responses

from exoscale_connector.resources.private_network import PrivateNetwork, PrivateNetworkClient


@responses.activate
def test_list_parses_typed_models(client, base_url) -> None:
    responses.add(
        responses.GET,
        f"{base_url}/private-network",
        json={
            "private-networks": [
                {"id": "pn1", "name": "mgmt"},
                {"id": "pn2", "name": "storage"},
            ]
        },
        status=200,
    )
    nets = PrivateNetworkClient(client).list()
    assert [n.name for n in nets] == ["mgmt", "storage"]


@responses.activate
def test_get_returns_model(client, base_url) -> None:
    responses.add(
        responses.GET,
        f"{base_url}/private-network/pn1",
        json={
            "id": "pn1",
            "name": "mgmt",
            "description": "management network",
            "start-ip": "10.0.0.10",
            "end-ip": "10.0.0.200",
            "netmask": "255.255.255.0",
        },
        status=200,
    )
    net = PrivateNetworkClient(client).get("pn1")
    assert isinstance(net, PrivateNetwork)
    assert net.start_ip == "10.0.0.10"
    assert net.end_ip == "10.0.0.200"
    assert net.netmask == "255.255.255.0"


@responses.activate
def test_find_by_name(client, base_url) -> None:
    responses.add(
        responses.GET,
        f"{base_url}/private-network",
        json={"private-networks": [{"id": "pn1", "name": "mgmt"}]},
        status=200,
    )
    found = PrivateNetworkClient(client).find_by_name("MGMT")
    assert found is not None and found.id == "pn1"


@responses.activate
def test_find_by_name_returns_none_when_missing(client, base_url) -> None:
    responses.add(
        responses.GET,
        f"{base_url}/private-network",
        json={"private-networks": [{"id": "pn1", "name": "mgmt"}]},
        status=200,
    )
    assert PrivateNetworkClient(client).find_by_name("nonexistent") is None


@responses.activate
def test_create_awaits_operation_and_refetches(client, base_url) -> None:
    responses.add(
        responses.POST,
        f"{base_url}/private-network",
        json={"id": "op1", "state": "success", "reference": {"id": "pn-new"}},
        status=200,
    )
    responses.add(
        responses.GET,
        f"{base_url}/private-network/pn-new",
        json={"id": "pn-new", "name": "backend"},
        status=200,
    )
    created = PrivateNetworkClient(client).create({"name": "backend"})
    assert created.id == "pn-new"
    assert created.name == "backend"


@responses.activate
def test_delete_returns_settled_operation(client, base_url) -> None:
    responses.add(
        responses.DELETE,
        f"{base_url}/private-network/pn1",
        json={"id": "op9", "state": "pending"},
        status=200,
    )
    responses.add(
        responses.GET,
        f"{base_url}/operation/op9",
        json={"id": "op9", "state": "success"},
        status=200,
    )
    op = PrivateNetworkClient(client).delete("pn1")
    assert op.state == "success"


@responses.activate
def test_kebab_case_fields_deserialise_to_snake_case(client, base_url) -> None:
    """start-ip / end-ip from the API wire format must land on snake_case attributes."""
    responses.add(
        responses.GET,
        f"{base_url}/private-network/pn1",
        json={"id": "pn1", "name": "x", "start-ip": "192.168.1.1", "end-ip": "192.168.1.254"},
        status=200,
    )
    net = PrivateNetworkClient(client).get("pn1")
    assert net.start_ip == "192.168.1.1"
    assert net.end_ip == "192.168.1.254"


@responses.activate
def test_labels_field_parses(client, base_url) -> None:
    responses.add(
        responses.GET,
        f"{base_url}/private-network/pn1",
        json={"id": "pn1", "name": "x", "labels": {"zone": "de-fra-1"}},
        status=200,
    )
    net = PrivateNetworkClient(client).get("pn1")
    assert net.labels == {"zone": "de-fra-1"}


@responses.activate
def test_attach_instance_puts_colon_action(client, base_url) -> None:
    responses.add(
        responses.PUT,
        f"{base_url}/private-network/pn1:attach",
        json={"id": "op-attach", "state": "success"},
        status=200,
    )
    op = PrivateNetworkClient(client).attach_instance("pn1", "i-abc")
    assert op.state == "success"
    sent = responses.calls[0].request.body
    assert b'"instance"' in sent and b'"i-abc"' in sent
    # No static lease requested -> no ip key in the body.
    assert b'"ip"' not in sent


@responses.activate
def test_attach_instance_with_static_ip(client, base_url) -> None:
    responses.add(
        responses.PUT,
        f"{base_url}/private-network/pn1:attach",
        json={"id": "op-attach2", "state": "success"},
        status=200,
    )
    op = PrivateNetworkClient(client).attach_instance("pn1", "i-abc", ip="10.0.0.42")
    assert op.state == "success"
    sent = responses.calls[0].request.body
    assert b'"ip"' in sent and b'"10.0.0.42"' in sent


@responses.activate
def test_attach_instance_awaits_pending_operation(client, base_url) -> None:
    responses.add(
        responses.PUT,
        f"{base_url}/private-network/pn1:attach",
        json={"id": "op-attach3", "state": "pending"},
        status=200,
    )
    responses.add(
        responses.GET,
        f"{base_url}/operation/op-attach3",
        json={"id": "op-attach3", "state": "success"},
        status=200,
    )
    op = PrivateNetworkClient(client).attach_instance("pn1", "i-abc")
    assert op.state == "success"


@responses.activate
def test_detach_instance_puts_colon_action(client, base_url) -> None:
    responses.add(
        responses.PUT,
        f"{base_url}/private-network/pn1:detach",
        json={"id": "op-detach", "state": "success"},
        status=200,
    )
    op = PrivateNetworkClient(client).detach_instance("pn1", "i-abc")
    assert op.state == "success"
    sent = responses.calls[0].request.body
    assert b'"instance"' in sent and b'"i-abc"' in sent
