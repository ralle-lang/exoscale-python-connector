"""Unit tests for DBaaSServiceClient.

All HTTP calls are intercepted by the ``responses`` library — no network
access.  Test coverage:

- list():        GET /dbaas-service, parse "dbaas-services" array
- get():         GET /dbaas-service/{name}, parse single service
- create():      POST /dbaas-{type}/{name} (type-specific endpoint) then
                 re-fetch via GET /dbaas-service/{name}
- delete():      DELETE /dbaas-service/{name}, wrap response in Operation
"""

from __future__ import annotations

import json

import pytest
import responses

from exoscale_connector.resources.dbaas import DBaaSServiceClient

# ---------------------------------------------------------------------------
# list
# ---------------------------------------------------------------------------


@responses.activate
def test_list_returns_all_services(client, base_url) -> None:
    responses.add(
        responses.GET,
        f"{base_url}/dbaas-service",
        json={
            "dbaas-services": [
                {"name": "pg-prod", "type": "pg", "state": "running"},
                {"name": "redis-cache", "type": "redis", "state": "running"},
            ]
        },
        status=200,
    )
    services = DBaaSServiceClient(client).list()
    assert len(services) == 2
    assert services[0].name == "pg-prod"
    assert services[1].name == "redis-cache"


@responses.activate
def test_list_returns_empty_list_when_no_services(client, base_url) -> None:
    responses.add(
        responses.GET,
        f"{base_url}/dbaas-service",
        json={"dbaas-services": []},
        status=200,
    )
    services = DBaaSServiceClient(client).list()
    assert services == []


# ---------------------------------------------------------------------------
# get
# ---------------------------------------------------------------------------


@responses.activate
def test_get_fetches_service_by_name(client, base_url) -> None:
    """get() does a two-step lookup: list -> find type -> type-specific detail.

    GET /dbaas-service/{name} returns 404 on the live API (the generic path is
    list-only), so the override lists, finds the service's type by name, then
    fetches the full body via dbaas-{long-type}/{name}.
    """
    # Step 1: list to discover the type.
    responses.add(
        responses.GET,
        f"{base_url}/dbaas-service",
        json={"dbaas-services": [{"name": "pg-prod", "type": "pg"}]},
        status=200,
    )
    # Step 2: type-specific GET for the detail body (pg -> postgres).
    responses.add(
        responses.GET,
        f"{base_url}/dbaas-postgres/pg-prod",
        json={"name": "pg-prod", "type": "pg", "plan": "startup-4", "state": "running"},
        status=200,
    )
    svc = DBaaSServiceClient(client).get("pg-prod")
    assert svc.name == "pg-prod"
    assert svc.type == "pg"
    assert svc.plan == "startup-4"
    assert svc.state == "running"


@responses.activate
def test_get_parses_typed_ip_filter(client, base_url) -> None:
    """ip-filter (wire key) deserialises onto the typed ip_filter field."""
    responses.add(
        responses.GET,
        f"{base_url}/dbaas-service",
        json={"dbaas-services": [{"name": "pg-prod", "type": "pg"}]},
        status=200,
    )
    responses.add(
        responses.GET,
        f"{base_url}/dbaas-postgres/pg-prod",
        json={"name": "pg-prod", "type": "pg", "ip-filter": ["203.0.113.0/24", "198.51.100.7/32"]},
        status=200,
    )
    svc = DBaaSServiceClient(client).get("pg-prod")
    assert svc.ip_filter == ["203.0.113.0/24", "198.51.100.7/32"]


@responses.activate
def test_create_sends_ip_filter_in_payload(client, base_url) -> None:
    """A typed/dict ip-filter is forwarded on the create payload."""
    responses.add(
        responses.POST,
        f"{base_url}/dbaas-postgres/locked-db",
        json={},
        status=200,
    )
    responses.add(
        responses.GET,
        f"{base_url}/dbaas-postgres/locked-db",
        json={"name": "locked-db", "type": "pg", "ip-filter": ["203.0.113.0/24"]},
        status=200,
    )
    svc = DBaaSServiceClient(client).create(
        {"plan": "hobbyist-2", "ip-filter": ["203.0.113.0/24"]},
        service_type="pg",
        name="locked-db",
    )
    sent = responses.calls[0].request.body
    assert b'"ip-filter"' in sent and b'"203.0.113.0/24"' in sent
    assert svc.ip_filter == ["203.0.113.0/24"]


@responses.activate
def test_get_preserves_extra_type_specific_fields(client, base_url) -> None:
    """Unknown/type-specific fields survive via extra='allow'."""
    responses.add(
        responses.GET,
        f"{base_url}/dbaas-service",
        json={"dbaas-services": [{"name": "pg-prod", "type": "pg"}]},
        status=200,
    )
    responses.add(
        responses.GET,
        f"{base_url}/dbaas-postgres/pg-prod",
        json={"name": "pg-prod", "pg-settings": {"max_connections": 100}},
        status=200,
    )
    svc = DBaaSServiceClient(client).get("pg-prod")
    # extra fields are accessible via model_extra
    assert svc.model_extra.get("pg-settings") == {"max_connections": 100}


@responses.activate
def test_get_raises_not_found_when_service_absent(client, base_url) -> None:
    """If the service isn't in the listing, get() raises NotFoundError."""
    from exoscale_connector.errors import NotFoundError

    responses.add(
        responses.GET,
        f"{base_url}/dbaas-service",
        json={"dbaas-services": [{"name": "other", "type": "mysql"}]},
        status=200,
    )
    with pytest.raises(NotFoundError):
        DBaaSServiceClient(client).get("does-not-exist")


# ---------------------------------------------------------------------------
# create
# ---------------------------------------------------------------------------


@responses.activate
def test_create_posts_to_type_specific_endpoint_then_refetches(client, base_url) -> None:
    """create() POSTs to dbaas-{long-type}/{name} then re-fetches via dbaas-service/{name}.

    Caller passes the short type ``"pg"`` (matching what ``list_service_types``
    returns); the connector translates to the URL form ``postgres`` because
    Exoscale's create endpoint uses the long name there.
    """
    # Step 1: type-specific create POST — caller used "pg", URL has "postgres".
    responses.add(
        responses.POST,
        f"{base_url}/dbaas-postgres/new-db",
        json={"name": "new-db", "type": "pg", "state": "rebuilding"},
        status=200,
    )
    # Step 2: re-fetch via the SAME type-specific endpoint (the generic
    # /dbaas-service/<name> is list-only and 404s on individual GETs).
    responses.add(
        responses.GET,
        f"{base_url}/dbaas-postgres/new-db",
        json={"name": "new-db", "type": "pg", "plan": "startup-4", "state": "running"},
        status=200,
    )

    svc = DBaaSServiceClient(client).create(
        {"plan": "startup-4"},
        service_type="pg",
        name="new-db",
    )

    assert svc.name == "new-db"
    assert svc.state == "running"
    # Verify the POST went to the long-form type-specific endpoint
    assert responses.calls[0].request.method == "POST"
    assert responses.calls[0].request.url.endswith("/dbaas-postgres/new-db")
    # Verify the payload was forwarded
    body = json.loads(responses.calls[0].request.body)
    assert body.get("plan") == "startup-4"


@responses.activate
def test_create_accepts_long_type_name_too(client, base_url) -> None:
    """Callers may also pass the long type name (e.g. ``postgres``) directly."""
    responses.add(
        responses.POST,
        f"{base_url}/dbaas-postgres/long-name-db",
        json={"name": "long-name-db", "type": "pg"},
        status=200,
    )
    responses.add(
        responses.GET,
        f"{base_url}/dbaas-postgres/long-name-db",
        json={"name": "long-name-db", "type": "pg", "state": "running"},
        status=200,
    )
    DBaaSServiceClient(client).create(
        {"plan": "startup-4"},
        service_type="postgres",  # already the URL form — no translation needed
        name="long-name-db",
    )
    assert responses.calls[0].request.url.endswith("/dbaas-postgres/long-name-db")


@responses.activate
def test_create_sends_empty_body_when_no_payload(client, base_url) -> None:
    """An empty dict payload results in a body-less (or empty-body) POST."""
    responses.add(
        responses.POST,
        f"{base_url}/dbaas-redis/cache1",
        json={"name": "cache1", "type": "redis", "state": "rebuilding"},
        status=200,
    )
    responses.add(
        responses.GET,
        f"{base_url}/dbaas-redis/cache1",
        json={"name": "cache1", "type": "redis", "state": "running"},
        status=200,
    )

    svc = DBaaSServiceClient(client).create(
        {},
        service_type="redis",
        name="cache1",
    )
    assert svc.name == "cache1"


@responses.activate
def test_create_uses_correct_type_in_url(client, base_url) -> None:
    """The service_type parameter is reflected verbatim in the POST path."""
    responses.add(
        responses.POST,
        f"{base_url}/dbaas-opensearch/search-svc",
        json={"name": "search-svc", "type": "opensearch", "state": "rebuilding"},
        status=200,
    )
    responses.add(
        responses.GET,
        f"{base_url}/dbaas-opensearch/search-svc",
        json={"name": "search-svc", "type": "opensearch", "state": "running"},
        status=200,
    )

    DBaaSServiceClient(client).create(
        {"plan": "hobbyist-2"},
        service_type="opensearch",
        name="search-svc",
    )
    # First call must be the type-specific POST
    assert "/dbaas-opensearch/search-svc" in responses.calls[0].request.url


# ---------------------------------------------------------------------------
# delete
# ---------------------------------------------------------------------------


@responses.activate
def test_delete_calls_generic_delete_endpoint(client, base_url) -> None:
    """delete() uses dbaas-service/{name}, not a type-specific path."""
    responses.add(
        responses.DELETE,
        f"{base_url}/dbaas-service/pg-prod",
        json={"id": "op-del-1", "state": "success"},
        status=200,
    )
    op = DBaaSServiceClient(client).delete("pg-prod")
    assert op.state == "success"
    assert responses.calls[0].request.url.endswith("/dbaas-service/pg-prod")


@responses.activate
def test_delete_wraps_response_in_operation(client, base_url) -> None:
    """The Operation model is returned even when delete is synchronous."""
    responses.add(
        responses.DELETE,
        f"{base_url}/dbaas-service/old-db",
        # DBaaS deletes often return a minimal or empty response; simulate that.
        json={"id": "op-del-2", "state": "success"},
        status=200,
    )
    op = DBaaSServiceClient(client).delete("old-db")
    assert op.id == "op-del-2"
    assert op.state == "success"


@responses.activate
def test_update_puts_to_type_specific_endpoint_and_refetches(client, base_url) -> None:
    responses.add(
        responses.PUT,
        f"{base_url}/dbaas-postgres/my-db",
        json={},
        status=200,
    )
    responses.add(
        responses.GET,
        f"{base_url}/dbaas-postgres/my-db",
        json={"name": "my-db", "type": "pg", "plan": "startup-8"},
        status=200,
    )
    svc = DBaaSServiceClient(client).update("my-db", {"plan": "startup-8"}, service_type="pg")
    assert svc.plan == "startup-8"
    assert json.loads(responses.calls[0].request.body) == {"plan": "startup-8"}


@responses.activate
def test_create_user_posts_username(client, base_url) -> None:
    responses.add(
        responses.POST,
        f"{base_url}/dbaas-postgres/my-db/user",
        json={"username": "analyst"},
        status=200,
    )
    result = DBaaSServiceClient(client).create_user("my-db", "analyst", service_type="pg")
    assert result == {"username": "analyst"}
    assert json.loads(responses.calls[0].request.body) == {"username": "analyst"}


@responses.activate
def test_delete_user_hits_user_path(client, base_url) -> None:
    responses.add(
        responses.DELETE,
        f"{base_url}/dbaas-postgres/my-db/user/analyst",
        json={},
        status=200,
    )
    DBaaSServiceClient(client).delete_user("my-db", "analyst", service_type="pg")
    assert responses.calls[0].request.method == "DELETE"


@responses.activate
def test_reset_user_password_uses_reset_path(client, base_url) -> None:
    responses.add(
        responses.PUT,
        f"{base_url}/dbaas-postgres/my-db/user/analyst/password/reset",
        json={},
        status=200,
    )
    DBaaSServiceClient(client).reset_user_password("my-db", "analyst", service_type="pg")
    assert responses.calls[0].request.method == "PUT"


def test_ensure_is_not_supported(client) -> None:
    with pytest.raises(NotImplementedError):
        DBaaSServiceClient(client).ensure({"name": "my-db"})


@responses.activate
def test_get_settings_uses_short_type_form(client, base_url) -> None:
    """get_settings hits /dbaas-settings-{short-type} (no pg->postgres aliasing)."""
    responses.add(
        responses.GET,
        f"{base_url}/dbaas-settings-clickhouse",
        json={"settings": {"clickhouse": {"foo": "bar"}}},
        status=200,
    )
    out = DBaaSServiceClient(client).get_settings("clickhouse")
    assert out == {"settings": {"clickhouse": {"foo": "bar"}}}


@responses.activate
def test_get_settings_short_form_for_pg(client, base_url) -> None:
    # pg stays "pg" for the settings endpoint (short form), unlike CRUD paths.
    responses.add(
        responses.GET,
        f"{base_url}/dbaas-settings-pg",
        json={"settings": {}},
        status=200,
    )
    assert DBaaSServiceClient(client).get_settings("pg") == {"settings": {}}


@responses.activate
def test_get_acl_config_uses_long_type_path(client, base_url) -> None:
    responses.add(
        responses.GET,
        f"{base_url}/dbaas-clickhouse/ch1/acl-config",
        json={"users": [{"username": "reader"}]},
        status=200,
    )
    out = DBaaSServiceClient(client).get_acl_config("ch1", service_type="clickhouse")
    assert out["users"][0]["username"] == "reader"


@responses.activate
def test_start_maintenance_puts_type_specific_path(client, base_url) -> None:
    responses.add(
        responses.PUT,
        f"{base_url}/dbaas-mysql/my1/maintenance/start",
        json={"id": "op1", "state": "success"},
        status=200,
    )
    out = DBaaSServiceClient(client).start_maintenance("my1", service_type="mysql")
    assert out["state"] == "success"


@responses.activate
def test_get_parses_version_field(client, base_url) -> None:
    # Two-step get: list to discover type, then type-specific detail carries version.
    responses.add(
        responses.GET,
        f"{base_url}/dbaas-service",
        json={"dbaas-services": [{"name": "my1", "type": "mysql"}]},
        status=200,
    )
    responses.add(
        responses.GET,
        f"{base_url}/dbaas-mysql/my1",
        json={"name": "my1", "type": "mysql", "version": "8", "plan": "hobbyist-2"},
        status=200,
    )
    svc = DBaaSServiceClient(client).get("my1")
    assert svc.version == "8"
