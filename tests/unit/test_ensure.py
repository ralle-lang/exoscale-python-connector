"""Unit tests for ResourceClient.ensure() and label-filtered list()."""
from __future__ import annotations

import pytest
import responses

from exoscale_connector.resources.instance import InstanceClient
from exoscale_connector.resources.security_group import SecurityGroupClient


@responses.activate
def test_ensure_creates_when_absent(client, base_url) -> None:
    responses.add(
        responses.GET, f"{base_url}/security-group", json={"security-groups": []}, status=200
    )
    responses.add(
        responses.POST,
        f"{base_url}/security-group",
        json={"id": "sg-1", "name": "web"},
        status=200,
    )
    sg = SecurityGroupClient(client).ensure({"name": "web"})
    assert sg.id == "sg-1"
    assert responses.calls[1].request.method == "POST"


@responses.activate
def test_ensure_returns_existing_without_mutating(client, base_url) -> None:
    responses.add(
        responses.GET,
        f"{base_url}/security-group",
        json={"security-groups": [{"id": "sg-1", "name": "web"}]},
        status=200,
    )
    sg = SecurityGroupClient(client).ensure({"name": "web"})
    assert sg.id == "sg-1"
    assert len(responses.calls) == 1  # lookup only — no POST/PUT


@responses.activate
def test_ensure_update_true_puts_payload(client, base_url) -> None:
    responses.add(
        responses.GET,
        f"{base_url}/security-group",
        json={"security-groups": [{"id": "sg-1", "name": "web"}]},
        status=200,
    )
    responses.add(
        responses.PUT,
        f"{base_url}/security-group/sg-1",
        json={"id": "sg-1", "name": "web", "description": "updated"},
        status=200,
    )
    sg = SecurityGroupClient(client).ensure({"name": "web", "description": "updated"}, update=True)
    assert sg.description == "updated"


def test_ensure_requires_a_name(client) -> None:
    with pytest.raises(ValueError):
        SecurityGroupClient(client).ensure({"description": "nameless"})


@responses.activate
def test_list_filters_by_labels(client, base_url) -> None:
    responses.add(
        responses.GET,
        f"{base_url}/instance",
        json={
            "instances": [
                {"id": "i-1", "name": "a", "labels": {"env": "prod", "team": "core"}},
                {"id": "i-2", "name": "b", "labels": {"env": "dev"}},
                {"id": "i-3", "name": "c"},
            ]
        },
        status=200,
    )
    matched = InstanceClient(client).list(labels={"env": "prod"})
    assert [i.id for i in matched] == ["i-1"]


@responses.activate
def test_list_without_labels_returns_everything(client, base_url) -> None:
    responses.add(
        responses.GET,
        f"{base_url}/instance",
        json={"instances": [{"id": "i-1"}, {"id": "i-2"}]},
        status=200,
    )
    assert len(InstanceClient(client).list()) == 2
