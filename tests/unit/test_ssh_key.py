"""Unit tests for SSHKeyClient."""

from __future__ import annotations

import responses

from exoscale_connector.resources.ssh_key import SSHKey, SSHKeyClient


@responses.activate
def test_list_parses_typed_models(client, base_url) -> None:
    responses.add(
        responses.GET,
        f"{base_url}/ssh-key",
        json={
            "ssh-keys": [
                {"name": "laptop", "fingerprint": "aa:bb:cc"},
                {"name": "ci-server", "fingerprint": "dd:ee:ff"},
            ]
        },
        status=200,
    )
    keys = SSHKeyClient(client).list()
    assert [k.name for k in keys] == ["laptop", "ci-server"]


@responses.activate
def test_find_by_name(client, base_url) -> None:
    responses.add(
        responses.GET,
        f"{base_url}/ssh-key",
        json={"ssh-keys": [{"name": "laptop", "fingerprint": "aa:bb:cc"}]},
        status=200,
    )
    found = SSHKeyClient(client).find_by_name("LAPTOP")
    assert found is not None
    assert found.fingerprint == "aa:bb:cc"


@responses.activate
def test_find_by_name_missing_returns_none(client, base_url) -> None:
    responses.add(
        responses.GET,
        f"{base_url}/ssh-key",
        json={"ssh-keys": []},
        status=200,
    )
    assert SSHKeyClient(client).find_by_name("ghost") is None


@responses.activate
def test_get_by_name(client, base_url) -> None:
    # SSH keys use name (not UUID) in the item path.
    responses.add(
        responses.GET,
        f"{base_url}/ssh-key/laptop",
        json={"name": "laptop", "fingerprint": "aa:bb:cc", "public-key": "ssh-ed25519 AAAA..."},
        status=200,
    )
    key = SSHKeyClient(client).get("laptop")
    assert isinstance(key, SSHKey)
    assert key.name == "laptop"
    assert key.public_key == "ssh-ed25519 AAAA..."


@responses.activate
def test_create_direct_resource_response(client, base_url) -> None:
    # SSH key import returns the resource directly (no async operation envelope).
    responses.add(
        responses.POST,
        f"{base_url}/ssh-key",
        json={"name": "laptop", "fingerprint": "aa:bb:cc"},
        status=200,
    )
    created = SSHKeyClient(client).create({"name": "laptop", "public-key": "ssh-ed25519 AAAA..."})
    assert isinstance(created, SSHKey)
    assert created.name == "laptop"
    # One call only: no operation poll or re-fetch.
    assert len(responses.calls) == 1


@responses.activate
def test_create_sends_kebab_payload(client, base_url) -> None:
    responses.add(
        responses.POST,
        f"{base_url}/ssh-key",
        json={"name": "laptop", "fingerprint": "aa:bb:cc"},
        status=200,
    )
    SSHKeyClient(client).create({"name": "laptop", "public-key": "ssh-ed25519 AAAA..."})
    body = responses.calls[0].request.body
    assert b'"public-key"' in body


@responses.activate
def test_create_operation_without_reference_refetches_by_name(client, base_url) -> None:
    """Regression: the live API returns ``{id, state}`` with no ``reference``.

    Since ssh-key is name-keyed (id_field="name"), the base ``create`` must fall
    back to the payload's name to re-fetch — otherwise it parses the operation
    envelope as the resource and the caller gets back an empty SSHKey.
    """
    # Async operation envelope: state already settled, no reference present.
    responses.add(
        responses.POST,
        f"{base_url}/ssh-key",
        json={"id": "op-no-ref", "state": "success"},
        status=200,
    )
    # The re-fetch must hit /ssh-key/<name> with the name from the create payload.
    responses.add(
        responses.GET,
        f"{base_url}/ssh-key/laptop",
        json={"name": "laptop", "fingerprint": "aa:bb:cc"},
        status=200,
    )
    created = SSHKeyClient(client).create({"name": "laptop", "public-key": "ssh-ed25519 AAAA..."})
    assert created.name == "laptop"
    assert created.fingerprint == "aa:bb:cc"


@responses.activate
def test_delete_by_name(client, base_url) -> None:
    # Delete uses the name as the path segment.
    responses.add(
        responses.DELETE,
        f"{base_url}/ssh-key/laptop",
        json={"id": "op77", "state": "pending"},
        status=200,
    )
    responses.add(
        responses.GET,
        f"{base_url}/operation/op77",
        json={"id": "op77", "state": "success"},
        status=200,
    )
    op = SSHKeyClient(client).delete("laptop")
    assert op.state == "success"
