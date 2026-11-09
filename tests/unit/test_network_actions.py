"""Unit tests for the colon actions on security groups, elastic IPs and private networks."""

from __future__ import annotations

import json

import pytest
import responses

from exoscale_connector.resources.elastic_ip import ElasticIPClient
from exoscale_connector.resources.private_network import PrivateNetworkClient
from exoscale_connector.resources.security_group import SecurityGroupClient

INSTANCE = {"instance": {"id": "i-1"}}


@pytest.mark.parametrize(
    ("call", "path", "body"),
    [
        (
            lambda c: SecurityGroupClient(c).attach_instance("g", "i-1"),
            "security-group/g:attach",
            INSTANCE,
        ),
        (
            lambda c: SecurityGroupClient(c).detach_instance("g", "i-1"),
            "security-group/g:detach",
            INSTANCE,
        ),
        (
            lambda c: SecurityGroupClient(c).add_external_source("g", "198.51.100.0/24"),
            "security-group/g:add-source",
            {"cidr": "198.51.100.0/24"},
        ),
        (
            lambda c: SecurityGroupClient(c).remove_external_source("g", "198.51.100.0/24"),
            "security-group/g:remove-source",
            {"cidr": "198.51.100.0/24"},
        ),
        (lambda c: ElasticIPClient(c).attach_instance("e", "i-1"), "elastic-ip/e:attach", INSTANCE),
        (lambda c: ElasticIPClient(c).detach_instance("e", "i-1"), "elastic-ip/e:detach", INSTANCE),
        (
            lambda c: PrivateNetworkClient(c).update_instance_ip("n", "i-1", "10.0.0.20"),
            "private-network/n:update-ip",
            {"instance": {"id": "i-1"}, "ip": "10.0.0.20"},
        ),
    ],
)
@responses.activate
def test_network_actions_put_expected_body(client, base_url, call, path, body) -> None:
    responses.add(responses.PUT, f"{base_url}/{path}", json={"id": "op", "state": "success"})
    assert call(client).state == "success"
    assert json.loads(responses.calls[0].request.body) == body
