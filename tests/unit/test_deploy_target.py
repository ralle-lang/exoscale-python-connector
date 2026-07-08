"""Unit tests for DeployTargetClient (read-only asset)."""
from __future__ import annotations

import responses

from exoscale_connector.resources.deploy_target import DeployTargetClient


@responses.activate
def test_list_returns_typed_models(client, base_url) -> None:
    responses.add(
        responses.GET,
        f"{base_url}/deploy-target",
        json={
            "deploy-targets": [
                {"id": "dt1", "name": "edge-a", "type": "edge"},
                {"id": "dt2", "name": "ded-b", "type": "dedicated"},
            ]
        },
        status=200,
    )
    targets = DeployTargetClient(client).list()
    assert [(t.name, t.type) for t in targets] == [("edge-a", "edge"), ("ded-b", "dedicated")]


@responses.activate
def test_get_returns_typed_model(client, base_url) -> None:
    responses.add(
        responses.GET,
        f"{base_url}/deploy-target/dt1",
        json={"id": "dt1", "name": "edge-a", "type": "edge", "description": "west edge"},
        status=200,
    )
    target = DeployTargetClient(client).get("dt1")
    assert target.id == "dt1"
    assert target.type == "edge"
    assert target.description == "west edge"
