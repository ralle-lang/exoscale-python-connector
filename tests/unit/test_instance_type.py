"""Unit tests for the instance-type client."""
from __future__ import annotations

import responses

from exoscale_connector.resources.instance_type import InstanceTypeClient


@responses.activate
def test_find_resolves_family_size_slug(client, base_url) -> None:
    responses.add(
        responses.GET,
        f"{base_url}/instance-type",
        json={
            "instance-types": [
                {"id": "it-1", "family": "standard", "size": "tiny", "cpus": 1},
                {"id": "it-2", "family": "standard", "size": "medium", "cpus": 4},
            ]
        },
        status=200,
    )
    found = InstanceTypeClient(client).find("Standard.Tiny")
    assert found is not None and found.id == "it-1"
    assert found.slug == "standard.tiny"


@responses.activate
def test_find_returns_none_when_absent(client, base_url) -> None:
    responses.add(
        responses.GET, f"{base_url}/instance-type", json={"instance-types": []}, status=200
    )
    assert InstanceTypeClient(client).find("gpu.huge") is None
