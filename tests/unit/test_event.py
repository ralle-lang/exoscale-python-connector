"""Unit tests for EventClient (read-only audit log)."""
from __future__ import annotations

import responses

from exoscale_connector.resources.event import EventClient


@responses.activate
def test_list_parses_bare_array_response(client, base_url) -> None:
    # GET /event returns a bare JSON array (no {"events": [...]} envelope).
    responses.add(
        responses.GET,
        f"{base_url}/event",
        json=[
            {"timestamp": "2026-07-08T10:00:00Z", "status": 200, "uri": "/instance"},
            {"timestamp": "2026-07-08T10:01:00Z", "status": 404, "uri": "/instance/x"},
        ],
        status=200,
    )
    events = EventClient(client).list()
    assert [e.status for e in events] == [200, 404]
    assert events[0].uri == "/instance"


@responses.activate
def test_list_maps_identity_references(client, base_url) -> None:
    responses.add(
        responses.GET,
        f"{base_url}/event",
        json=[{"timestamp": "t", "iam-user": {"id": "u1"}, "iam-api-key": {"id": "k1"}}],
        status=200,
    )
    (event,) = EventClient(client).list()
    assert event.iam_user.id == "u1"
    assert event.iam_api_key.id == "k1"


@responses.activate
def test_list_passes_from_and_to_query_params(client, base_url) -> None:
    responses.add(
        responses.GET,
        f"{base_url}/event",
        json=[],
        status=200,
        match=[
            responses.matchers.query_param_matcher(
                {"from": "2026-07-01T00:00:00Z", "to": "2026-07-08T00:00:00Z"}
            )
        ],
    )
    result = EventClient(client).list(from_="2026-07-01T00:00:00Z", to="2026-07-08T00:00:00Z")
    assert result == []
