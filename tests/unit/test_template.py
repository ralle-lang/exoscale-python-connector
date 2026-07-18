"""Unit tests for the template client."""

from __future__ import annotations

import responses

from exoscale_connector.resources.template import TemplateClient


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
