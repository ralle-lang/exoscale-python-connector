"""Unit tests for LoadBalancerClient (including service sub-resource methods)."""

from __future__ import annotations

import responses

from exoscale_connector.resources.load_balancer import (
    LoadBalancer,
    LoadBalancerClient,
    LoadBalancerService,
)


@responses.activate
def test_list_parses_typed_models(client, base_url) -> None:
    responses.add(
        responses.GET,
        f"{base_url}/load-balancer",
        json={
            "load-balancers": [
                {"id": "lb1", "name": "frontend"},
                {"id": "lb2", "name": "backend"},
            ]
        },
        status=200,
    )
    lbs = LoadBalancerClient(client).list()
    assert [lb.name for lb in lbs] == ["frontend", "backend"]


@responses.activate
def test_get_returns_model_with_services(client, base_url) -> None:
    responses.add(
        responses.GET,
        f"{base_url}/load-balancer/lb1",
        json={
            "id": "lb1",
            "name": "frontend",
            "ip": "1.2.3.4",
            "services": [{"id": "svc1", "name": "https", "port": 443, "target-port": 8443}],
        },
        status=200,
    )
    lb = LoadBalancerClient(client).get("lb1")
    assert isinstance(lb, LoadBalancer)
    assert lb.ip == "1.2.3.4"
    assert len(lb.services) == 1
    svc = lb.services[0]
    assert isinstance(svc, LoadBalancerService)
    assert svc.port == 443
    assert svc.target_port == 8443


@responses.activate
def test_find_by_name(client, base_url) -> None:
    responses.add(
        responses.GET,
        f"{base_url}/load-balancer",
        json={"load-balancers": [{"id": "lb1", "name": "frontend"}]},
        status=200,
    )
    found = LoadBalancerClient(client).find_by_name("FRONTEND")
    assert found is not None and found.id == "lb1"


@responses.activate
def test_create_awaits_operation_and_refetches(client, base_url) -> None:
    responses.add(
        responses.POST,
        f"{base_url}/load-balancer",
        json={"id": "op1", "state": "success", "reference": {"id": "lb-new"}},
        status=200,
    )
    responses.add(
        responses.GET,
        f"{base_url}/load-balancer/lb-new",
        json={"id": "lb-new", "name": "new-lb"},
        status=200,
    )
    created = LoadBalancerClient(client).create({"name": "new-lb"})
    assert created.id == "lb-new"
    assert created.name == "new-lb"


@responses.activate
def test_delete_returns_settled_operation(client, base_url) -> None:
    responses.add(
        responses.DELETE,
        f"{base_url}/load-balancer/lb1",
        json={"id": "op9", "state": "pending"},
        status=200,
    )
    responses.add(
        responses.GET,
        f"{base_url}/operation/op9",
        json={"id": "op9", "state": "success"},
        status=200,
    )
    op = LoadBalancerClient(client).delete("lb1")
    assert op.state == "success"


@responses.activate
def test_add_service_posts_kebab_payload(client, base_url) -> None:
    """add_service must POST to load-balancer/{lb_id}/service with kebab-case body."""
    responses.add(
        responses.POST,
        f"{base_url}/load-balancer/lb1/service",
        json={"id": "op2", "state": "success"},
        status=200,
    )
    svc = LoadBalancerService(
        name="https",
        protocol="tcp",
        port=443,
        target_port=8443,
        strategy="round-robin",
    )
    LoadBalancerClient(client).add_service("lb1", svc)
    sent = responses.calls[0].request.body
    # Verify kebab-case serialisation of snake_case fields
    assert b'"target-port": 8443' in sent
    assert b'"strategy": "round-robin"' in sent
    assert b'"port": 443' in sent


@responses.activate
def test_add_service_from_dict(client, base_url) -> None:
    """add_service should also accept a plain dict payload."""
    responses.add(
        responses.POST,
        f"{base_url}/load-balancer/lb1/service",
        json={"id": "op3", "state": "success"},
        status=200,
    )
    LoadBalancerClient(client).add_service(
        "lb1",
        {"name": "http", "protocol": "tcp", "port": 80, "target-port": 8080},
    )
    assert len(responses.calls) == 1


@responses.activate
def test_update_service_puts_to_correct_path(client, base_url) -> None:
    responses.add(
        responses.PUT,
        f"{base_url}/load-balancer/lb1/service/svc1",
        json={"id": "op4", "state": "success"},
        status=200,
    )
    op = LoadBalancerClient(client).update_service("lb1", "svc1", {"description": "updated"})
    assert op.state == "success"
    assert responses.calls[0].request.method == "PUT"


@responses.activate
def test_delete_service_deletes_correct_path(client, base_url) -> None:
    responses.add(
        responses.DELETE,
        f"{base_url}/load-balancer/lb1/service/svc1",
        json={"id": "op5", "state": "pending"},
        status=200,
    )
    responses.add(
        responses.GET,
        f"{base_url}/operation/op5",
        json={"id": "op5", "state": "success"},
        status=200,
    )
    op = LoadBalancerClient(client).delete_service("lb1", "svc1")
    assert op.state == "success"
    assert responses.calls[0].request.method == "DELETE"
