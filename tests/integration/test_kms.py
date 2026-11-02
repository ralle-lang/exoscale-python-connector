"""KMS live test — key lifecycle, rotation, and an envelope-crypto round-trip.

Gated separately from the numbered tiers because KMS keys **cannot be deleted
immediately**: the only teardown is ``schedule_deletion``, whose minimum
``delay-days`` is 7. Every run therefore leaves one key in ``pending-deletion``
for ~7 days (Exoscale removes it after the window). Opt in explicitly:

    EXOSCALE_RUN_LIVE_TESTS=1
    EXOSCALE_ALLOW_MUTATION=1
    EXOSCALE_TEST_KMS=1
    EXOSCALE_API_KEY / EXOSCALE_API_SECRET / EXOSCALE_TEST_ZONE

Secrets (plaintext, data keys) are asserted for presence only and never printed.
"""

from __future__ import annotations

import base64
import os

import pytest

from exoscale_connector.errors import APIError
from exoscale_connector.resources.kms import KmsKeyClient

from ._fixtures import assert_safe_name, make_name

pytestmark = pytest.mark.integration


def _env_bool(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


@pytest.fixture
def kms_enabled(require_mutation_allowed) -> None:
    if not _env_bool("EXOSCALE_TEST_KMS"):
        pytest.skip("KMS live test disabled (set EXOSCALE_TEST_KMS=1 to enable)")


def test_kms_key_lifecycle(live_client, run_id, tracker, kms_enabled) -> None:
    """State, rotation, crypto, data keys and the deletion lifecycle on one key."""
    kms = KmsKeyClient(live_client)
    name = make_name(run_id, "kms")[:50]

    # Create. KMS access is gated per tenant/credential — the product may be
    # off ("... not enabled") or the API key's IAM role may not grant it
    # ("Forbidden by role policy for kms"). Either way it's a 403 access gate,
    # not a connector fault: skip rather than fail.
    try:
        key = kms.create({"name": name, "usage": "encrypt-decrypt"})
    except APIError as exc:
        if exc.status_code == 403:
            pytest.skip(f"KMS forbidden on this tenant/credential ({exc})")
        raise
    key_id = key.id
    assert key_id, "create did not return a key id"
    # Best-effort teardown: schedule deletion (min 7-day window — the key lingers).
    tracker.register("kms", lambda: kms.schedule_deletion(key_id, delay_days=7), key_id)

    assert kms.get(key_id).status == "enabled"

    # State: a disabled key refuses to encrypt.
    plaintext_b64 = base64.b64encode(b"connector-kms-smoke").decode()
    kms.disable(key_id)
    assert kms.get(key_id).status == "disabled"
    with pytest.raises(APIError):
        kms.encrypt(key_id, plaintext_b64)
    kms.enable(key_id)
    assert kms.get(key_id).status == "enabled"

    # Rotation: new keys already rotate yearly; re-enabling while on is a 400,
    # so changing the period means disable first.
    rotation = kms.get(key_id).rotation
    assert rotation is not None and rotation.automatic is True
    assert rotation.rotation_period == 365
    assert kms.disable_rotation(key_id)["rotation"]["automatic"] is False
    enabled = kms.enable_rotation(key_id, rotation_period=90)["rotation"]
    assert enabled["automatic"] is True and enabled["rotation-period"] == 90
    kms.rotate(key_id)
    rotations = kms.list_rotations(key_id)
    assert isinstance(rotations, list) and rotations, "expected at least one rotation"

    # Envelope crypto round-trip. plaintext/ciphertext are Base64 on the wire.
    context = base64.b64encode(b"connector-ctx").decode()
    enc = kms.encrypt(key_id, plaintext_b64, encryption_context=context)
    assert enc.get("ciphertext"), "encrypt returned no ciphertext"
    dec = kms.decrypt(key_id, enc["ciphertext"], encryption_context=context)
    assert dec.get("plaintext") == plaintext_b64, "decrypt did not round-trip the plaintext"

    # Re-encrypt dropping the context; the result decrypts without one.
    re_enc = kms.re_encrypt(
        key_id,
        source={"key": key_id, "ciphertext": enc["ciphertext"], "encryption-context": context},
        destination={"key": key_id},
    )
    assert kms.decrypt(key_id, re_enc["ciphertext"]).get("plaintext") == plaintext_b64

    # Data keys, sized by spec or by byte count: assert without ever printing them.
    dk = kms.generate_data_key(key_id)
    assert dk.get("ciphertext") and dk.get("plaintext"), "generate-data-key missing a part"
    assert len(base64.b64decode(dk["plaintext"])) == 32
    dk16 = kms.generate_data_key(key_id, bytes_count=16)
    assert len(base64.b64decode(dk16["plaintext"])) == 16

    # Deletion lifecycle (no immediate delete — the final schedule lingers).
    assert_safe_name(name)
    assert kms.schedule_deletion(key_id, delay_days=7).get("delete-at")
    assert kms.get(key_id).status == "pending-deletion"
    kms.cancel_deletion(key_id)
    # Cancelling restores the key disabled, not enabled.
    assert kms.get(key_id).status == "disabled"
    kms.enable(key_id)
    sched = kms.schedule_deletion(key_id, delay_days=7)
    assert sched.get("delete-at"), "schedule-deletion returned no delete-at"
    # The key is now pending-deletion; leave the tracked cleanup as a no-op re-schedule.
    tracker.unregister(key_id)
