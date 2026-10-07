"""Unit tests for the read-only zone client."""

from __future__ import annotations

import responses

from exoscale_connector.resources.zone import ZoneClient


@responses.activate
def test_list_zones(client, base_url) -> None:
    responses.add(
        responses.GET,
        f"{base_url}/zone",
        json={"zones": [{"name": "de-fra-1"}, {"name": "at-vie-2"}]},
        status=200,
    )
    zones = ZoneClient(client).list()
    assert [z.name for z in zones] == ["de-fra-1", "at-vie-2"]


@responses.activate
def test_list_zones_is_sent_unsigned(client, base_url) -> None:
    # GET /zone is public, but a signed request is checked against the key's
    # IAM policy, so a least-privilege key would get 403 on a public listing.
    responses.add(responses.GET, f"{base_url}/zone", json={"zones": []}, status=200)
    ZoneClient(client).list()
    assert "Authorization" not in responses.calls[0].request.headers
