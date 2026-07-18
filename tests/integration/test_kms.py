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
    """Create → rotate → encrypt/decrypt round-trip → schedule deletion."""
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

    # Rotation
    kms.enable_rotation(key_id, rotation_period=30)
    kms.rotate(key_id)
    rotations = kms.list_rotations(key_id)
    assert isinstance(rotations, list) and rotations, "expected at least one rotation"

    # Envelope crypto round-trip. plaintext/ciphertext are Base64 on the wire.
    plaintext_b64 = base64.b64encode(b"connector-kms-smoke").decode()
    enc = kms.encrypt(key_id, plaintext_b64)
    assert enc.get("ciphertext"), "encrypt returned no ciphertext"
    dec = kms.decrypt(key_id, enc["ciphertext"])
    assert dec.get("plaintext") == plaintext_b64, "decrypt did not round-trip the plaintext"

    # Data key: assert both parts present without ever printing them.
    dk = kms.generate_data_key(key_id, key_spec="AES-256")
    assert dk.get("ciphertext") and dk.get("plaintext"), "generate-data-key missing a part"

    # Deletion lifecycle (no immediate delete — this schedules and lingers).
    assert_safe_name(name)
    sched = kms.schedule_deletion(key_id, delay_days=7)
    assert sched.get("delete-at"), "schedule-deletion returned no delete-at"
    # The key is now pending-deletion; leave the tracked cleanup as a no-op re-schedule.
    tracker.unregister(key_id)
