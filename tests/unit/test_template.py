"""Unit tests for the template client."""

from __future__ import annotations

import json

import responses

from exoscale_connector.resources.template import Template, TemplateClient


@responses.activate
def test_list_passes_visibility_param(client, base_url) -> None:
    responses.add(
        responses.GET,
        f"{base_url}/template",
        json={"templates": [{"id": "t-1", "name": "my-image", "visibility": "private"}]},
        status=200,
        match=[responses.matchers.query_param_matcher({"visibility": "private"})],
    )
    templates = TemplateClient(client).list(visibility="private")
    assert templates[0].id == "t-1"


@responses.activate
def test_list_without_visibility_sends_no_params(client, base_url) -> None:
    responses.add(
        responses.GET,
        f"{base_url}/template",
        json={"templates": []},
        status=200,
        match=[responses.matchers.query_param_matcher({})],
    )
    assert TemplateClient(client).list() == []


@responses.activate
def test_find_linux_prefers_smallest(client, base_url) -> None:
    responses.add(
        responses.GET,
        f"{base_url}/template",
        json={
            "templates": [
                {"id": "t-big", "family": "Linux Ubuntu", "size": 50_000_000_000},
                {"id": "t-small", "family": "Linux Debian", "size": 10_000_000_000},
                {"id": "t-win", "family": "Windows Server", "size": 1},
            ]
        },
        status=200,
    )
    found = TemplateClient(client).find_linux()
    assert found is not None and found.id == "t-small"


@responses.activate
def test_copy_posts_target_zone(client, base_url) -> None:
    responses.add(
        responses.POST,
        f"{base_url}/template/t-1",
        json={"id": "op", "state": "success", "reference": {"id": "t-copy"}},
    )
    op = TemplateClient(client).copy("t-1", "ch-gva-2")
    assert op.reference_id == "t-copy"
    assert json.loads(responses.calls[0].request.body) == {"target-zone": {"name": "ch-gva-2"}}


def test_template_parses_maintainer_and_zones() -> None:
    t = Template.model_validate(
        {
            "maintainer": "Exoscale",
            "application-consistent-snapshot-enabled": True,
            "zones": ["at-vie-1"],
        }
    )
    assert t.maintainer == "Exoscale" and t.application_consistent_snapshot_enabled
    assert t.zones == ["at-vie-1"]
