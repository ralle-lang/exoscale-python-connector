"""Unit tests for KmsKeyClient.

All HTTP is intercepted by ``responses``; no network calls are made. KMS is
synchronous (no async operations), so no operation-poll mocks are needed.
"""

from __future__ import annotations

import json

import pytest
import responses

from exoscale_connector.resources.kms import KmsKey, KmsKeyClient


@responses.activate
def test_list_returns_typed_models(client, base_url) -> None:
    responses.add(
        responses.GET,
        f"{base_url}/kms-key",
        json={
            "kms-keys": [
                {"id": "k1", "name": "a", "status": "enabled"},
                {"id": "k2", "name": "b", "status": "disabled"},
            ]
        },
        status=200,
    )
    keys = KmsKeyClient(client).list()
    assert [(k.name, k.status) for k in keys] == [("a", "enabled"), ("b", "disabled")]


@responses.activate
def test_get_parses_nested_rotation(client, base_url) -> None:
    responses.add(
        responses.GET,
        f"{base_url}/kms-key/k1",
        json={
            "id": "k1",
            "name": "a",
            "status": "enabled",
            "multi-zone": True,
            "origin-zone": "de-fra-1",
            "rotation": {"automatic": True, "rotation-period": 90, "manual-count": 2},
            "replicas": ["at-vie-1"],
        },
        status=200,
    )
    key = KmsKeyClient(client).get("k1")
    assert key.multi_zone is True
    assert key.origin_zone == "de-fra-1"
    assert key.rotation is not None and key.rotation.rotation_period == 90
    assert key.replicas == ["at-vie-1"]


@responses.activate
def test_create_returns_key_directly(client, base_url) -> None:
    # KMS create returns the key body (no async operation envelope).
    responses.add(
        responses.POST,
        f"{base_url}/kms-key",
        json={"id": "k-new", "name": "app-key", "status": "enabled", "usage": "encrypt-decrypt"},
        status=200,
    )
    created = KmsKeyClient(client).create(KmsKey(name="app-key", usage="encrypt-decrypt"))
    assert created.id == "k-new"
    assert created.status == "enabled"
    sent = json.loads(responses.calls[0].request.body)
    assert sent["name"] == "app-key" and sent["usage"] == "encrypt-decrypt"


def test_delete_raises_not_implemented(client) -> None:
    with pytest.raises(NotImplementedError, match="schedule_deletion"):
        KmsKeyClient(client).delete("k1")


@responses.activate
def test_enable_disable(client, base_url) -> None:
    responses.add(
        responses.POST, f"{base_url}/kms-key/k1/enable", json={"status": "success"}, status=200
    )
    responses.add(
        responses.POST, f"{base_url}/kms-key/k1/disable", json={"status": "success"}, status=200
    )
    kms = KmsKeyClient(client)
    assert kms.enable("k1")["status"] == "success"
    assert kms.disable("k1")["status"] == "success"


@responses.activate
def test_rotation_methods(client, base_url) -> None:
    responses.add(
        responses.POST,
        f"{base_url}/kms-key/k1/enable-key-rotation",
        json={"rotation": {"automatic": True, "rotation-period": 30}},
        status=200,
    )
    responses.add(
        responses.POST,
        f"{base_url}/kms-key/k1/disable-key-rotation",
        json={"rotation": {"automatic": False}},
        status=200,
    )
    responses.add(
        responses.POST,
        f"{base_url}/kms-key/k1/rotate",
        json={"rotation": {"automatic": False, "manual-count": 1}},
        status=200,
    )
    responses.add(
        responses.GET,
        f"{base_url}/kms-key/k1/list-key-rotations",
        json={"rotations": [{"version": 1, "automatic": False, "rotated-at": "t"}]},
        status=200,
    )
    kms = KmsKeyClient(client)
    assert kms.enable_rotation("k1", rotation_period=30)["rotation"]["rotation-period"] == 30
    # rotation_period omitted -> body-less POST
    kms.enable_rotation("k1")
    assert responses.calls[1].request.body is None
    assert kms.disable_rotation("k1")["rotation"]["automatic"] is False
    assert kms.rotate("k1")["rotation"]["manual-count"] == 1
    rotations = kms.list_rotations("k1")
    assert rotations[0]["version"] == 1


@responses.activate
def test_crypto_roundtrip_payloads(client, base_url) -> None:
    responses.add(
        responses.POST, f"{base_url}/kms-key/k1/encrypt", json={"ciphertext": "CT"}, status=200
    )
    responses.add(
        responses.POST, f"{base_url}/kms-key/k1/decrypt", json={"plaintext": "PT"}, status=200
    )
    responses.add(
        responses.POST,
        f"{base_url}/kms-key/k1/generate-data-key",
        json={"ciphertext": "CT", "plaintext": "DK"},
        status=200,
    )
    kms = KmsKeyClient(client)
    enc = kms.encrypt("k1", "PT", encryption_context="CTX")
    assert enc["ciphertext"] == "CT"
    assert json.loads(responses.calls[0].request.body) == {
        "plaintext": "PT",
        "encryption-context": "CTX",
    }
    dec = kms.decrypt("k1", "CT")
    assert dec["plaintext"] == "PT"
    assert json.loads(responses.calls[1].request.body) == {"ciphertext": "CT"}
    dk = kms.generate_data_key("k1", key_spec="AES-256", bytes_count=32)
    assert dk["plaintext"] == "DK" and dk["ciphertext"] == "CT"
    assert json.loads(responses.calls[2].request.body) == {"key-spec": "AES-256", "bytes-count": 32}


@responses.activate
def test_re_encrypt_sends_source_and_destination(client, base_url) -> None:
    responses.add(
        responses.POST, f"{base_url}/kms-key/k1/re-encrypt", json={"ciphertext": "CT2"}, status=200
    )
    out = KmsKeyClient(client).re_encrypt(
        "k1", source={"ciphertext": "CT"}, destination={"encryption-context": "CTX"}
    )
    assert out["ciphertext"] == "CT2"
    assert json.loads(responses.calls[0].request.body) == {
        "source": {"ciphertext": "CT"},
        "destination": {"encryption-context": "CTX"},
    }


@responses.activate
def test_deletion_lifecycle(client, base_url) -> None:
    responses.add(
        responses.POST,
        f"{base_url}/kms-key/k1/schedule-deletion",
        json={"delete-at": "2026-07-15T00:00:00Z"},
        status=200,
    )
    responses.add(
        responses.POST,
        f"{base_url}/kms-key/k1/cancel-deletion",
        json={"status": "success"},
        status=200,
    )
    kms = KmsKeyClient(client)
    sched = kms.schedule_deletion("k1", delay_days=7)
    assert sched["delete-at"].startswith("2026-07-15")
    assert json.loads(responses.calls[0].request.body) == {"delay-days": 7}
    assert kms.cancel_deletion("k1")["status"] == "success"


@responses.activate
def test_replicate_sends_target_zone(client, base_url) -> None:
    responses.add(
        responses.POST,
        f"{base_url}/kms-key/k1/replicate",
        json={"status": "target-registered"},
        status=200,
    )
    out = KmsKeyClient(client).replicate("k1", "at-vie-1")
    assert out["status"] == "target-registered"
    assert json.loads(responses.calls[0].request.body) == {"zone": "at-vie-1"}
