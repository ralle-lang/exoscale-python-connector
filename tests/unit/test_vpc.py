"""Unit tests for VpcClient (VPC + subnet + route sub-resources).

All HTTP is intercepted by ``responses``; no network calls are made.
"""

from __future__ import annotations

import json

import responses

from exoscale_connector.resources.vpc import VpcClient, VpcRoute, VpcSubnet


@responses.activate
def test_list_vpcs_returns_typed_models(client, base_url) -> None:
    responses.add(
        responses.GET,
        f"{base_url}/vpc",
        json={"vpcs": [{"id": "v1", "name": "prod"}, {"id": "v2", "name": "dev"}]},
        status=200,
    )
    vpcs = VpcClient(client).list()
    assert [v.name for v in vpcs] == ["prod", "dev"]


@responses.activate
def test_create_vpc_awaits_operation(client, base_url) -> None:
    responses.add(
        responses.POST,
        f"{base_url}/vpc",
        json={"id": "op1", "state": "pending"},
        status=200,
    )
    responses.add(
        responses.GET,
        f"{base_url}/operation/op1",
        json={"id": "op1", "state": "success", "reference": {"id": "v-new"}},
        status=200,
    )
    # POST /vpc returns an operation; base create re-fetches the referenced VPC.
    responses.add(
        responses.GET,
        f"{base_url}/vpc/v-new",
        json={"id": "v-new", "name": "prod"},
        status=200,
    )
    created = VpcClient(client).create({"name": "prod"})
    assert created.id == "v-new"


@responses.activate
def test_list_subnets_returns_typed_models(client, base_url) -> None:
    responses.add(
        responses.GET,
        f"{base_url}/vpc/v1/subnet",
        json={"subnets": [{"id": "s1", "name": "app", "ipv4-block": "10.0.0.0/24"}]},
        status=200,
    )
    subnets = VpcClient(client).list_subnets("v1")
    assert isinstance(subnets[0], VpcSubnet)
    assert subnets[0].ipv4_block == "10.0.0.0/24"


@responses.activate
def test_create_subnet_sends_kebab_payload_and_awaits(client, base_url) -> None:
    responses.add(
        responses.POST,
        f"{base_url}/vpc/v1/subnet",
        json={"id": "op2", "state": "pending"},
        status=200,
    )
    responses.add(
        responses.GET,
        f"{base_url}/operation/op2",
        json={"id": "op2", "state": "success", "reference": {"id": "s-new"}},
        status=200,
    )
    op = VpcClient(client).create_subnet(
        "v1",
        VpcSubnet(
            name="app", addressfamily="inet4", address_space="private", ipv4_block="10.0.0.0/24"
        ),
    )
    assert op.state == "success" and op.reference_id == "s-new"
    sent = json.loads(responses.calls[0].request.body)
    # snake_case model fields serialised as kebab-case on the wire.
    assert sent["address-space"] == "private"
    assert sent["ipv4-block"] == "10.0.0.0/24"


@responses.activate
def test_attach_subnet_sends_instance_ref(client, base_url) -> None:
    responses.add(
        responses.PUT,
        f"{base_url}/vpc/v1/subnet/s1/attach",
        json={"id": "op3", "state": "success"},
        status=200,
    )
    op = VpcClient(client).attach_subnet("v1", "s1", "i-123")
    assert op.state == "success"
    sent = json.loads(responses.calls[0].request.body)
    assert sent == {"instance": {"id": "i-123"}}


@responses.activate
def test_create_route_omits_name(client, base_url) -> None:
    responses.add(
        responses.POST,
        f"{base_url}/vpc/v1/subnet/s1/route",
        json={"id": "op4", "state": "success"},
        status=200,
    )
    op = VpcClient(client).create_route(
        "v1",
        "s1",
        VpcRoute(destination="0.0.0.0/0", target="10.0.0.1"),
    )
    assert op.state == "success"
    sent = json.loads(responses.calls[0].request.body)
    assert sent == {"destination": "0.0.0.0/0", "target": "10.0.0.1"}
    assert "name" not in sent


@responses.activate
def test_list_routes_returns_typed_models(client, base_url) -> None:
    responses.add(
        responses.GET,
        f"{base_url}/vpc/v1/route",
        json={"routes": [{"id": "r1", "destination": "10.1.0.0/16", "target": "10.0.0.1"}]},
        status=200,
    )
    routes = VpcClient(client).list_routes("v1")
    assert isinstance(routes[0], VpcRoute)
    assert routes[0].destination == "10.1.0.0/16"


@responses.activate
def test_delete_subnet_returns_settled_operation(client, base_url) -> None:
    responses.add(
        responses.DELETE,
        f"{base_url}/vpc/v1/subnet/s1",
        json={"id": "op5", "state": "pending"},
        status=200,
    )
    responses.add(
        responses.GET,
        f"{base_url}/operation/op5",
        json={"id": "op5", "state": "success"},
        status=200,
    )
    op = VpcClient(client).delete_subnet("v1", "s1")
    assert op.state == "success"
