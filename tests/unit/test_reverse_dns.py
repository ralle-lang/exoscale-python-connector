"""Unit tests for instance scale and the reverse-DNS mixin (instance + elastic IP)."""
from __future__ import annotations

import json as jsonlib

import responses

from exoscale_connector.resources.elastic_ip import ElasticIPClient
from exoscale_connector.resources.instance import InstanceClient


@responses.activate
def test_scale_sends_target_type_and_awaits(client, base_url) -> None:
    responses.add(
        responses.PUT,
        f"{base_url}/instance/i-1:scale",
        json={"id": "op1", "state": "pending"},
        status=200,
    )
    responses.add(
        responses.GET,
        f"{base_url}/operation/op1",
        json={"id": "op1", "state": "success"},
        status=200,
    )
    op = InstanceClient(client).scale("i-1", "it-2")
    assert op.state == "success"
    body = jsonlib.loads(responses.calls[0].request.body)
    assert body == {"instance-type": {"id": "it-2"}}


@responses.activate
def test_get_reverse_dns_returns_domain(client, base_url) -> None:
    responses.add(
        responses.GET,
        f"{base_url}/reverse-dns/instance/i-1",
        json={"domain-name": "host.example.com."},
        status=200,
    )
    assert InstanceClient(client).get_reverse_dns("i-1") == "host.example.com."


@responses.activate
def test_get_reverse_dns_unwraps_nested_record(client, base_url) -> None:
    responses.add(
        responses.GET,
        f"{base_url}/reverse-dns/elastic-ip/eip-1",
        json={"domain-name": {"domain-name": "mail.example.com."}},
        status=200,
    )
    assert ElasticIPClient(client).get_reverse_dns("eip-1") == "mail.example.com."


@responses.activate
def test_get_reverse_dns_none_when_unset(client, base_url) -> None:
    responses.add(
        responses.GET,
        f"{base_url}/reverse-dns/instance/i-1",
        json={"message": "not found"},
        status=404,
    )
    assert InstanceClient(client).get_reverse_dns("i-1") is None


@responses.activate
def test_set_reverse_dns_puts_domain_and_awaits(client, base_url) -> None:
    responses.add(
        responses.PUT,
        f"{base_url}/reverse-dns/elastic-ip/eip-1",
        json={"id": "op2", "state": "pending"},
        status=200,
    )
    responses.add(
        responses.GET,
        f"{base_url}/operation/op2",
        json={"id": "op2", "state": "success"},
        status=200,
    )
    op = ElasticIPClient(client).set_reverse_dns("eip-1", "mail.example.com.")
    assert op.state == "success"
    body = jsonlib.loads(responses.calls[0].request.body)
    assert body == {"domain-name": "mail.example.com."}


@responses.activate
def test_delete_reverse_dns(client, base_url) -> None:
    responses.add(
        responses.DELETE,
        f"{base_url}/reverse-dns/instance/i-1",
        json={"id": "op3", "state": "success"},
        status=200,
    )
    op = InstanceClient(client).delete_reverse_dns("i-1")
    assert op.state == "success"
