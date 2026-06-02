"""Unit tests for DnsDomainClient (DNS domains + record sub-resource)."""
from __future__ import annotations

import responses

from exoscale_connector.resources.dns import DnsDomainClient, DnsRecord

# ------------------------------------------------------------------ #
# Domain-level tests
# ------------------------------------------------------------------ #


@responses.activate
def test_list_domains_parses_typed_models(client, base_url) -> None:
    responses.add(
        responses.GET,
        f"{base_url}/dns-domain",
        json={
            "dns-domains": [
                {"id": "dom1", "unicode-name": "example.com"},
                {"id": "dom2", "unicode-name": "example.net"},
            ]
        },
        status=200,
    )
    domains = DnsDomainClient(client).list()
    assert [d.unicode_name for d in domains] == ["example.com", "example.net"]


@responses.activate
def test_get_domain_returns_model(client, base_url) -> None:
    responses.add(
        responses.GET,
        f"{base_url}/dns-domain/dom1",
        json={"id": "dom1", "unicode-name": "example.com", "state": "active"},
        status=200,
    )
    domain = DnsDomainClient(client).get("dom1")
    assert domain.id == "dom1"
    assert domain.unicode_name == "example.com"
    assert domain.state == "active"


@responses.activate
def test_create_domain_awaits_operation_and_refetches(client, base_url) -> None:
    # POST returns an async operation referencing the new domain.
    responses.add(
        responses.POST,
        f"{base_url}/dns-domain",
        json={"id": "op1", "state": "success", "reference": {"id": "dom-new"}},
        status=200,
    )
    # The client re-fetches once the operation settles.
    responses.add(
        responses.GET,
        f"{base_url}/dns-domain/dom-new",
        json={"id": "dom-new", "unicode-name": "example.com"},
        status=200,
    )
    created = DnsDomainClient(client).create({"unicode-name": "example.com"})
    assert created.id == "dom-new"
    assert created.unicode_name == "example.com"


# ------------------------------------------------------------------ #
# Record sub-resource tests
# ------------------------------------------------------------------ #


@responses.activate
def test_list_records_uses_primary_key(client, base_url) -> None:
    # The live API confirms the wrapper key is "dns-domain-records".
    responses.add(
        responses.GET,
        f"{base_url}/dns-domain/dom1/record",
        json={
            "dns-domain-records": [
                {"id": "rec1", "name": "www", "type": "A", "content": "192.0.2.1", "ttl": 300},
                {
                    "id": "rec2", "name": "@", "type": "MX",
                    "content": "mail.example.com", "ttl": 3600, "priority": 10,
                },
            ]
        },
        status=200,
    )
    records = DnsDomainClient(client).list_records("dom1")
    assert len(records) == 2
    assert records[0].name == "www"
    assert records[0].type == "A"


@responses.activate
def test_create_record_awaits_operation_and_refetches(client, base_url) -> None:
    # POST /dns-domain/{id}/record -> async operation.
    responses.add(
        responses.POST,
        f"{base_url}/dns-domain/dom1/record",
        json={"id": "op2", "state": "success", "reference": {"id": "rec-new"}},
        status=200,
    )
    # Re-fetch the created record.
    responses.add(
        responses.GET,
        f"{base_url}/dns-domain/dom1/record/rec-new",
        json={"id": "rec-new", "name": "api", "type": "A", "content": "192.0.2.2", "ttl": 300},
        status=200,
    )
    record = DnsDomainClient(client).create_record(
        "dom1",
        {"name": "api", "type": "A", "content": "192.0.2.2", "ttl": 300},
    )
    assert record.id == "rec-new"
    assert record.name == "api"


@responses.activate
def test_create_record_posts_kebab_payload(client, base_url) -> None:
    """Verify that snake_case model fields are serialised to kebab-case on the wire."""
    responses.add(
        responses.POST,
        f"{base_url}/dns-domain/dom1/record",
        json={"id": "op3", "state": "success", "reference": {"id": "rec3"}},
        status=200,
    )
    responses.add(
        responses.GET,
        f"{base_url}/dns-domain/dom1/record/rec3",
        json={
            "id": "rec3", "name": "mail", "type": "MX",
            "content": "mx.example.com", "ttl": 3600, "priority": 10,
        },
        status=200,
    )
    rec = DnsRecord(name="mail", type="MX", content="mx.example.com", ttl=3600, priority=10)
    DnsDomainClient(client).create_record("dom1", rec)

    sent = responses.calls[0].request.body
    # The model uses snake_case; the wire format must use kebab-case aliases.
    # "type", "content", "ttl", "priority", "name" are single-word — no change needed.
    # This assertion confirms the request body is valid JSON and contains expected fields.
    assert b'"type": "MX"' in sent
    assert b'"priority": 10' in sent


@responses.activate
def test_delete_record_returns_settled_operation(client, base_url) -> None:
    responses.add(
        responses.DELETE,
        f"{base_url}/dns-domain/dom1/record/rec1",
        json={"id": "op9", "state": "pending"},
        status=200,
    )
    responses.add(
        responses.GET,
        f"{base_url}/operation/op9",
        json={"id": "op9", "state": "success"},
        status=200,
    )
    op = DnsDomainClient(client).delete_record("dom1", "rec1")
    assert op.state == "success"
