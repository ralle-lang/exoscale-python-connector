"""Unit tests for IAMUserClient."""
from __future__ import annotations

import responses

from exoscale_connector.resources.iam_user import IAMUser, IAMUserClient


@responses.activate
def test_list_parses_typed_models(client, base_url) -> None:
    responses.add(
        responses.GET,
        f"{base_url}/user",
        json={
            "users": [
                {"id": "user-1", "email": "alice@example.com"},
                {"id": "user-2", "email": "bob@example.com"},
            ]
        },
        status=200,
    )
    users = IAMUserClient(client).list()
    assert [u.email for u in users] == ["alice@example.com", "bob@example.com"]


@responses.activate
def test_find_by_email(client, base_url) -> None:
    # name_field = "email", so find_by_name matches on email.
    responses.add(
        responses.GET,
        f"{base_url}/user",
        json={"users": [{"id": "user-1", "email": "alice@example.com"}]},
        status=200,
    )
    found = IAMUserClient(client).find_by_name("ALICE@EXAMPLE.COM")
    assert found is not None
    assert found.id == "user-1"


@responses.activate
def test_find_by_email_missing_returns_none(client, base_url) -> None:
    responses.add(
        responses.GET,
        f"{base_url}/user",
        json={"users": []},
        status=200,
    )
    assert IAMUserClient(client).find_by_name("nobody@example.com") is None


@responses.activate
def test_get_by_id(client, base_url) -> None:
    responses.add(
        responses.GET,
        f"{base_url}/user/user-1",
        json={"id": "user-1", "email": "alice@example.com", "role": {"id": "role-1"}},
        status=200,
    )
    user = IAMUserClient(client).get("user-1")
    assert isinstance(user, IAMUser)
    assert user.email == "alice@example.com"
    assert user.role is not None
    assert user.role.id == "role-1"


@responses.activate
def test_create_awaits_operation_and_refetches(client, base_url) -> None:
    responses.add(
        responses.POST,
        f"{base_url}/user",
        json={"id": "op1", "state": "success", "reference": {"id": "user-new"}},
        status=200,
    )
    responses.add(
        responses.GET,
        f"{base_url}/user/user-new",
        json={"id": "user-new", "email": "charlie@example.com"},
        status=200,
    )
    created = IAMUserClient(client).create({"email": "charlie@example.com"})
    assert created.id == "user-new"
    assert created.email == "charlie@example.com"


@responses.activate
def test_update_awaits_operation_and_refetches(client, base_url) -> None:
    responses.add(
        responses.PUT,
        f"{base_url}/user/user-1",
        json={"id": "op2", "state": "success", "reference": {"id": "user-1"}},
        status=200,
    )
    responses.add(
        responses.GET,
        f"{base_url}/user/user-1",
        json={"id": "user-1", "email": "alice@example.com", "role": {"id": "role-2"}},
        status=200,
    )
    updated = IAMUserClient(client).update("user-1", {"role": {"id": "role-2"}})
    assert updated.role is not None
    assert updated.role.id == "role-2"


@responses.activate
def test_delete_returns_settled_operation(client, base_url) -> None:
    responses.add(
        responses.DELETE,
        f"{base_url}/user/user-1",
        json={"id": "op9", "state": "pending"},
        status=200,
    )
    responses.add(
        responses.GET,
        f"{base_url}/operation/op9",
        json={"id": "op9", "state": "success"},
        status=200,
    )
    op = IAMUserClient(client).delete("user-1")
    assert op.state == "success"
