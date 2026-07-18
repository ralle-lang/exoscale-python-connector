"""Unit tests for ApiKeyClient."""

from __future__ import annotations

import responses

from exoscale_connector.resources.api_key import ApiKey, ApiKeyClient


@responses.activate
def test_list_parses_typed_models(client, base_url) -> None:
    responses.add(
        responses.GET,
        f"{base_url}/api-key",
        json={
            "api-keys": [
                {"key": "EXOabc123", "name": "ci-runner"},
                {"key": "EXOdef456", "name": "deploy-bot"},
            ]
        },
        status=200,
    )
    keys = ApiKeyClient(client).list()
    assert [k.name for k in keys] == ["ci-runner", "deploy-bot"]
    assert keys[0].key == "EXOabc123"


@responses.activate
def test_find_by_name(client, base_url) -> None:
    responses.add(
        responses.GET,
        f"{base_url}/api-key",
        json={"api-keys": [{"key": "EXOabc123", "name": "ci-runner"}]},
        status=200,
    )
    found = ApiKeyClient(client).find_by_name("CI-RUNNER")
    assert found is not None
    assert found.key == "EXOabc123"


@responses.activate
def test_find_by_name_missing_returns_none(client, base_url) -> None:
    responses.add(
        responses.GET,
        f"{base_url}/api-key",
        json={"api-keys": []},
        status=200,
    )
    assert ApiKeyClient(client).find_by_name("nope") is None


@responses.activate
def test_create_returns_direct_resource_with_secret(client, base_url) -> None:
    # POST /api-key is NOT async: the API returns the resource body directly,
    # including the one-time secret.
    responses.add(
        responses.POST,
        f"{base_url}/api-key",
        json={"key": "EXOnew789", "name": "my-key", "role-id": "role-uuid-1", "secret": "s3cr3t"},
        status=200,
    )
    created = ApiKeyClient(client).create({"name": "my-key", "role-id": "role-uuid-1"})
    assert isinstance(created, ApiKey)
    assert created.key == "EXOnew789"
    assert created.name == "my-key"
    # Secret must be captured on create.
    assert created.secret == "s3cr3t"
    # Only one HTTP call: no operation polling or re-fetch.
    assert len(responses.calls) == 1


@responses.activate
def test_create_sends_kebab_payload(client, base_url) -> None:
    responses.add(
        responses.POST,
        f"{base_url}/api-key",
        json={"key": "EXOnew789", "name": "my-key", "role-id": "role-uuid-1"},
        status=200,
    )
    ApiKeyClient(client).create({"name": "my-key", "role-id": "role-uuid-1"})
    body = responses.calls[0].request.body
    assert b'"role-id"' in body


@responses.activate
def test_get_by_key_id(client, base_url) -> None:
    responses.add(
        responses.GET,
        f"{base_url}/api-key/EXOabc123",
        json={"key": "EXOabc123", "name": "ci-runner"},
        status=200,
    )
    key = ApiKeyClient(client).get("EXOabc123")
    assert key.key == "EXOabc123"


@responses.activate
def test_delete_returns_settled_operation(client, base_url) -> None:
    responses.add(
        responses.DELETE,
        f"{base_url}/api-key/EXOabc123",
        json={"id": "op42", "state": "pending"},
        status=200,
    )
    responses.add(
        responses.GET,
        f"{base_url}/operation/op42",
        json={"id": "op42", "state": "success"},
        status=200,
    )
    op = ApiKeyClient(client).delete("EXOabc123")
    assert op.state == "success"


@responses.activate
def test_secret_absent_on_list(client, base_url) -> None:
    # Confirm that a list response without a secret field results in secret=None.
    responses.add(
        responses.GET,
        f"{base_url}/api-key",
        json={"api-keys": [{"key": "EXOabc123", "name": "ci-runner"}]},
        status=200,
    )
    keys = ApiKeyClient(client).list()
    assert keys[0].secret is None


def test_secret_is_masked_in_repr_but_kept_in_dump() -> None:
    # repr must never echo the live credential, but model_dump() is the
    # caller's one chance to capture it on create — it stays serialisable.
    created = ApiKey(key="EXOabc123", name="ci", secret="topsecretvalue")
    assert "topsecretvalue" not in repr(created)
    assert created.model_dump()["secret"] == "topsecretvalue"
