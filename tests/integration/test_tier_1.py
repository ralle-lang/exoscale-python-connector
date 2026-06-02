"""Tier 1 live tests — free, non-compute asset types.

Enabled only when the master mutation switch and the tier flag are both set:

    EXOSCALE_ALLOW_MUTATION=1
    EXOSCALE_TEST_TIER_1=1
    EXOSCALE_RUN_LIVE_TESTS=1
    EXOSCALE_API_KEY / EXOSCALE_API_SECRET / EXOSCALE_TEST_ZONE

Each test follows the same shape: provision → register with the tracker →
verify → mutate (where the API supports it) → cleanup → unregister. If a
test fails between provision and explicit delete, the tracker sweeps any
leakage on teardown.
"""
from __future__ import annotations

import pytest

from exoscale_connector.errors import APIError
from exoscale_connector.resources.anti_affinity_group import AntiAffinityGroupClient
from exoscale_connector.resources.api_key import ApiKeyClient
from exoscale_connector.resources.dns import DnsDomainClient
from exoscale_connector.resources.iam_role import IAMPolicy, IAMRole, IAMRoleClient
from exoscale_connector.resources.private_network import PrivateNetworkClient
from exoscale_connector.resources.security_group import (
    SecurityGroupClient,
    SecurityGroupRule,
)
from exoscale_connector.resources.ssh_key import SSHKey, SSHKeyClient

from ._fixtures import assert_safe_name, make_name

pytestmark = pytest.mark.integration


def test_security_group_lifecycle(live_client, run_id, tracker, tier_1_enabled) -> None:
    """Security group: create + rule add/delete + delete."""
    sg = SecurityGroupClient(live_client)
    name = make_name(run_id, "sg")
    created = sg.create({"name": name, "description": "connector tier-1 smoke"})
    assert created.id, "create did not return an id"
    sg_id = created.id
    tracker.register("security-group", lambda: sg.delete(sg_id), sg_id)

    fetched = sg.get(sg_id)
    assert fetched.name == name
    found = sg.find_by_name(name)
    assert found is not None and found.id == sg_id

    rule_desc = f"{name}-ingress-443"
    sg.add_rule(
        sg_id,
        SecurityGroupRule(
            flow_direction="ingress",
            protocol="tcp",
            start_port=443,
            end_port=443,
            network="0.0.0.0/0",
            description=rule_desc,
        ),
    )
    after_add = sg.get(sg_id)
    matches = [r for r in after_add.rules if r.description == rule_desc]
    assert len(matches) == 1, f"expected exactly one rule with description {rule_desc!r}"
    sg.delete_rule(sg_id, matches[0].id)
    after_del = sg.get(sg_id)
    assert not [r for r in after_del.rules if r.description == rule_desc]

    assert_safe_name(name)
    sg.delete(sg_id)
    tracker.unregister(sg_id)


def test_private_network_lifecycle(live_client, run_id, tracker, tier_1_enabled) -> None:
    """Private network: create + update + delete."""
    pn = PrivateNetworkClient(live_client)
    name = make_name(run_id, "pn")
    created = pn.create({"name": name, "description": "connector tier-1 smoke"})
    pn_id = created.id
    tracker.register("private-network", lambda: pn.delete(pn_id), pn_id)

    fetched = pn.get(pn_id)
    assert fetched.name == name
    found = pn.find_by_name(name)
    assert found is not None and found.id == pn_id

    pn.update(pn_id, {"description": "updated by tier-1 smoke"})
    after = pn.get(pn_id)
    assert after.description == "updated by tier-1 smoke"

    assert_safe_name(name)
    pn.delete(pn_id)
    tracker.unregister(pn_id)


def test_anti_affinity_group_lifecycle(live_client, run_id, tracker, tier_1_enabled) -> None:
    """Anti-affinity group: create + delete (API does not support update)."""
    aag = AntiAffinityGroupClient(live_client)
    name = make_name(run_id, "aag")
    created = aag.create({"name": name, "description": "connector tier-1 smoke"})
    aag_id = created.id
    tracker.register("anti-affinity-group", lambda: aag.delete(aag_id), aag_id)

    fetched = aag.get(aag_id)
    assert fetched.name == name
    found = aag.find_by_name(name)
    assert found is not None and found.id == aag_id

    assert_safe_name(name)
    aag.delete(aag_id)
    tracker.unregister(aag_id)


def test_ssh_key_lifecycle(live_client, run_id, tracker, tier_1_enabled) -> None:
    """SSH key: create + get + delete. Generates an ephemeral ed25519 keypair in memory."""
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

    # The private key is generated and discarded inside this process — it is
    # never written to disk and never logged.
    private = Ed25519PrivateKey.generate()
    public_openssh = private.public_key().public_bytes(
        Encoding.OpenSSH, PublicFormat.OpenSSH
    ).decode("ascii")

    name = make_name(run_id, "key")
    keys = SSHKeyClient(live_client)
    created = keys.create(SSHKey(name=name, public_key=f"{public_openssh} connector-tier-1"))
    assert created.name == name
    tracker.register("ssh-key", lambda: keys.delete(name), name)

    fetched = keys.get(name)
    assert fetched.name == name
    assert fetched.fingerprint, "API did not return a fingerprint"

    assert_safe_name(name)
    keys.delete(name)
    tracker.unregister(name)


def test_iam_role_lifecycle(live_client, run_id, tracker, tier_1_enabled) -> None:
    """IAM role: create with a deny-all policy + update + policy setters + delete."""
    roles = IAMRoleClient(live_client)
    name = make_name(run_id, "role")
    payload = IAMRole(
        name=name,
        description="connector tier-1 smoke",
        # A deny-all role is harmless even if the key were to leak somehow.
        policy=IAMPolicy(default_service_strategy="deny", services={}),
    )
    created = roles.create(payload)
    role_id = created.id
    tracker.register("iam-role", lambda: roles.delete(role_id), role_id)

    fetched = roles.get(role_id)
    assert fetched.name == name

    roles.update(role_id, {"description": "updated by tier-1 smoke"})
    after = roles.get(role_id)
    assert after.description == "updated by tier-1 smoke"

    # Exercise the dedicated policy sub-endpoints (PUT :policy / :assume-role-policy)
    # that the generic update() does not cover.
    roles.set_policy(role_id, IAMPolicy.allow_services(["compute"]))
    with_policy = roles.get(role_id)
    assert with_policy.policy is not None
    assert "compute" in (with_policy.policy.services or {})

    # assume-role-policy: Exoscale accepts the PUT but does not echo the policy
    # back on GET for an ordinary (non-assumable) role, so we verify the call is
    # accepted — set_assume_role_policy raises on an API/operation failure — rather
    # than asserting a GET round-trip.
    roles.set_assume_role_policy(role_id, IAMPolicy.deny_all())

    assert_safe_name(name)
    roles.delete(role_id)
    tracker.unregister(role_id)


def test_dns_lifecycle(live_client, run_id, tracker, tier_1_enabled) -> None:
    """DNS: create zone + add/update/delete A record + delete zone.

    The zone uses the reserved ``.test`` TLD (RFC 2606), so it is guaranteed not
    to collide with any real domain anywhere.
    """
    dns = DnsDomainClient(live_client)
    # Domain labels must be lowercase + [a-z0-9-]; make_run_id is already lowercase.
    domain_name = make_name(run_id, "dns").lower() + ".test"
    try:
        created = dns.create({"unicode-name": domain_name})
    except APIError as exc:
        # Account-level DNS quota is a tenant config, not a connector bug — skip
        # cleanly so the test isn't a noisy failure in tenants that are at-limit.
        if "subscription limit" in str(exc).lower():
            pytest.skip(f"tenant DNS quota exhausted: {exc}")
        raise
    domain_id = created.id
    tracker.register("dns-domain", lambda: dns.delete(domain_id), domain_id)

    fetched = dns.get(domain_id)
    assert fetched.unicode_name == domain_name

    record = dns.create_record(
        domain_id,
        {"name": "www", "type": "A", "content": "192.0.2.1", "ttl": 3600},
    )
    record_id = record.id
    assert record_id, "create_record did not return an id"
    # Register a deleter that runs only if the explicit delete below is skipped.
    tracker.register(
        "dns-record",
        lambda: dns.delete_record(domain_id, record_id),
        record_id,
    )

    listed = dns.list_records(domain_id)
    assert any(r.id == record_id for r in listed)

    dns.update_record(domain_id, record_id, {"ttl": 7200})
    updated = dns.get_record(domain_id, record_id)
    assert updated.ttl == 7200

    dns.delete_record(domain_id, record_id)
    tracker.unregister(record_id)

    assert_safe_name(domain_name)
    dns.delete(domain_id)
    tracker.unregister(domain_id)


def test_api_key_lifecycle(live_client, run_id, tracker, tier_1_api_key_enabled) -> None:
    """API key: create (bound to a temp deny-all role) -> assert secret -> delete.

    The create response is the ONLY time the secret is visible. The test
    asserts the secret is non-empty without ever printing it, then deletes
    both the key and the temporary role.
    """
    roles = IAMRoleClient(live_client)
    keys = ApiKeyClient(live_client)

    role_name = make_name(run_id, "role-for-key")
    role = roles.create(
        IAMRole(
            name=role_name,
            description="connector tier-1 api-key smoke",
            policy=IAMPolicy(default_service_strategy="deny", services={}),
        )
    )
    role_id = role.id
    assert role_id, "role create returned no id"
    tracker.register("iam-role", lambda: roles.delete(role_id), role_id)

    key_name = make_name(run_id, "apikey")
    created = keys.create({"name": key_name, "role-id": role_id})
    key_id = created.key
    assert key_id, "api-key create did not return a 'key' id"
    # The secret is returned exactly once — assert presence without printing.
    assert created.secret, "api-key create did not return a secret"
    tracker.register("api-key", lambda: keys.delete(key_id), key_id)

    # Listing never returns the secret again.
    listed = keys.list()
    matching = [k for k in listed if k.key == key_id]
    assert matching and not matching[0].secret

    assert_safe_name(key_name)
    keys.delete(key_id)
    tracker.unregister(key_id)

    roles.delete(role_id)
    tracker.unregister(role_id)

