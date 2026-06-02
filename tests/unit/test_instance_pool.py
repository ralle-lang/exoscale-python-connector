"""Unit tests for InstancePoolClient."""
from __future__ import annotations

import responses

from exoscale_connector.resources.instance_pool import InstancePoolClient


@responses.activate
def test_list_parses_typed_models(client, base_url) -> None:
    responses.add(
        responses.GET,
        f"{base_url}/instance-pool",
        json={
            "instance-pools": [
                {"id": "pool-1", "name": "workers", "size": 3},
                {"id": "pool-2", "name": "jobs", "size": 1},
            ]
        },
        status=200,
    )
    pools = InstancePoolClient(client).list()
    assert [p.name for p in pools] == ["workers", "jobs"]
    assert pools[0].size == 3


@responses.activate
def test_get_parses_references(client, base_url) -> None:
    responses.add(
        responses.GET,
        f"{base_url}/instance-pool/pool-1",
        json={
            "id": "pool-1",
            "name": "workers",
            "size": 3,
            "instance-type": {"id": "type-uuid"},
            "template": {"id": "tmpl-uuid"},
            "security-groups": [{"id": "sg-1"}],
            "instances": [{"id": "i-a"}, {"id": "i-b"}, {"id": "i-c"}],
        },
        status=200,
    )
    pool = InstancePoolClient(client).get("pool-1")
    assert pool.instance_type is not None and pool.instance_type.id == "type-uuid"
    assert len(pool.instances) == 3


@responses.activate
def test_find_by_name(client, base_url) -> None:
    responses.add(
        responses.GET,
        f"{base_url}/instance-pool",
        json={"instance-pools": [{"id": "pool-1", "name": "workers"}]},
        status=200,
    )
    found = InstancePoolClient(client).find_by_name("WORKERS")
    assert found is not None and found.id == "pool-1"


@responses.activate
def test_create_awaits_operation_and_refetches(client, base_url) -> None:
    responses.add(
        responses.POST,
        f"{base_url}/instance-pool",
        json={"id": "op1", "state": "success", "reference": {"id": "pool-new"}},
        status=200,
    )
    responses.add(
        responses.GET,
        f"{base_url}/instance-pool/pool-new",
        json={"id": "pool-new", "name": "new-pool", "size": 2},
        status=200,
    )
    pool = InstancePoolClient(client).create({"name": "new-pool", "size": 2})
    assert pool.id == "pool-new"
    assert pool.name == "new-pool"


@responses.activate
def test_delete_returns_settled_operation(client, base_url) -> None:
    responses.add(
        responses.DELETE,
        f"{base_url}/instance-pool/pool-1",
        json={"id": "op9", "state": "pending"},
        status=200,
    )
    responses.add(
        responses.GET,
        f"{base_url}/operation/op9",
        json={"id": "op9", "state": "success"},
        status=200,
    )
    op = InstancePoolClient(client).delete("pool-1")
    assert op.state == "success"


@responses.activate
def test_scale_puts_colon_action(client, base_url) -> None:
    responses.add(
        responses.PUT,
        f"{base_url}/instance-pool/pool-1:scale",
        json={"id": "op-scale", "state": "success"},
        status=200,
    )
    op = InstancePoolClient(client).scale("pool-1", 5)
    assert op.state == "success"
    # Verify the request body contained the correct size
    sent = responses.calls[0].request.body
    assert b'"size": 5' in sent or b'"size":5' in sent


@responses.activate
def test_scale_awaits_pending_operation(client, base_url) -> None:
    responses.add(
        responses.PUT,
        f"{base_url}/instance-pool/pool-1:scale",
        json={"id": "op-scale2", "state": "pending"},
        status=200,
    )
    responses.add(
        responses.GET,
        f"{base_url}/operation/op-scale2",
        json={"id": "op-scale2", "state": "success"},
        status=200,
    )
    op = InstancePoolClient(client).scale("pool-1", 3)
    assert op.state == "success"
