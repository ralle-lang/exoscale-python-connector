"""Tier 3 live tests — compute (smallest instance type, minutes of runtime).

Enabled by:

    EXOSCALE_ALLOW_MUTATION=1
    EXOSCALE_TEST_TIER_3=1
    EXOSCALE_RUN_LIVE_TESTS=1
    EXOSCALE_API_KEY / EXOSCALE_API_SECRET / EXOSCALE_TEST_ZONE

Covers:
  * Instance lifecycle (start / stop / reboot)
  * Instance pool scale 1 -> 2 -> 1
  * Compute snapshot created from an instance
  * Block-volume online ops (attach / resize / detach) — the operations Tier 2
    couldn't exercise because they need a running instance

Every test creates its own instance + deps (ssh-key, security-group) and tears
them down. Resources carry the conn-test- prefix; the tracker handles cleanup
even on failure.
"""

from __future__ import annotations

import time

import pytest

from exoscale_connector.errors import APIError
from exoscale_connector.resources.block_volume import BlockVolumeClient
from exoscale_connector.resources.instance import InstanceClient
from exoscale_connector.resources.instance_pool import InstancePoolClient
from exoscale_connector.resources.private_network import PrivateNetworkClient
from exoscale_connector.resources.security_group import SecurityGroupClient
from exoscale_connector.resources.snapshot import SnapshotClient
from exoscale_connector.resources.ssh_key import SSHKey, SSHKeyClient

from ._fixtures import (
    assert_safe_name,
    make_name,
    resolve_instance_type,
    resolve_linux_template,
    wait_for_state,
)

pytestmark = pytest.mark.integration


def _generate_ssh_pub() -> str:
    """Build an OpenSSH-format ed25519 public key from an ephemeral keypair."""
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

    private = Ed25519PrivateKey.generate()
    return private.public_key().public_bytes(Encoding.OpenSSH, PublicFormat.OpenSSH).decode("ascii")


def _make_deps(client, run_id: str, tracker):
    """Create a security group and an ssh-key for an instance, registered for cleanup."""
    sgs = SecurityGroupClient(client)
    keys = SSHKeyClient(client)

    sg_name = make_name(run_id, "sg")
    sg = sgs.create({"name": sg_name, "description": "tier-3 instance dep"})
    sg_id = sg.id
    assert sg_id, "security-group create returned no id"
    tracker.register("security-group", lambda: sgs.delete(sg_id), sg_id)

    key_name = make_name(run_id, "key")
    keys.create(SSHKey(name=key_name, public_key=f"{_generate_ssh_pub()} tier-3"))
    tracker.register("ssh-key", lambda: keys.delete(key_name), key_name)

    return sg_id, key_name


def _instance_payload(
    run_id: str,
    suffix: str,
    tiny_id: str,
    template_id: str,
    sg_id: str,
    ssh_key_name: str,
) -> dict:
    """Minimum-cost instance create payload (standard.tiny, 10 GiB disk)."""
    return {
        "name": make_name(run_id, suffix),
        "instance-type": {"id": tiny_id},
        "template": {"id": template_id},
        "disk-size": 10,
        "ssh-key": {"name": ssh_key_name},
        "security-groups": [{"id": sg_id}],
    }


def test_instance_lifecycle(tier_3_client, run_id, tracker, tier_3_enabled) -> None:
    """Instance: create + get + find + update labels + stop/start/reboot + delete."""
    sg_id, key_name = _make_deps(tier_3_client, run_id, tracker)
    tiny_id = resolve_instance_type(tier_3_client, "standard.tiny")
    template_id = resolve_linux_template(tier_3_client)

    instances = InstanceClient(tier_3_client)
    payload = _instance_payload(run_id, "instance", tiny_id, template_id, sg_id, key_name)
    created = instances.create(payload)
    inst_id = created.id
    assert inst_id, "create did not return an id"
    tracker.register("instance", lambda: instances.delete(inst_id), inst_id)

    # Wait until the freshly-created instance actually boots.
    running = wait_for_state(lambda: instances.get(inst_id), "running", timeout=600)
    assert running.name == payload["name"]
    found = instances.find_by_name(payload["name"])
    assert found is not None and found.id == inst_id

    instances.update(inst_id, {"labels": {"connector": "tier-3"}})
    after = instances.get(inst_id)
    assert (after.labels or {}).get("connector") == "tier-3"

    instances.stop(inst_id)
    wait_for_state(lambda: instances.get(inst_id), "stopped", timeout=300)
    instances.start(inst_id)
    wait_for_state(lambda: instances.get(inst_id), "running", timeout=300)
    instances.reboot(inst_id)
    # A reboot may briefly dip into "rebooting" before returning to "running".
    wait_for_state(lambda: instances.get(inst_id), "running", timeout=300)

    assert_safe_name(payload["name"])
    instances.delete(inst_id)
    tracker.unregister(inst_id)


def test_instance_pool_lifecycle(tier_3_client, run_id, tracker, tier_3_enabled) -> None:
    """Instance pool: create size=1 -> scale to 2 -> scale to 1 -> delete."""
    sg_id, key_name = _make_deps(tier_3_client, run_id, tracker)
    tiny_id = resolve_instance_type(tier_3_client, "standard.tiny")
    template_id = resolve_linux_template(tier_3_client)

    pools = InstancePoolClient(tier_3_client)
    name = make_name(run_id, "pool")
    payload = {
        "name": name,
        "description": "tier-3 pool",
        "size": 1,
        "instance-type": {"id": tiny_id},
        "template": {"id": template_id},
        "disk-size": 10,
        "ssh-key": {"name": key_name},
        "security-groups": [{"id": sg_id}],
    }
    created = pools.create(payload)
    pool_id = created.id
    assert pool_id
    tracker.register("instance-pool", lambda: pools.delete(pool_id), pool_id)

    wait_for_state(lambda: pools.get(pool_id), "running", timeout=600)
    pools.scale(pool_id, 2)
    pool_at_2 = wait_for_state(lambda: pools.get(pool_id), "running", timeout=600)
    assert pool_at_2.size == 2
    pools.scale(pool_id, 1)
    pool_at_1 = wait_for_state(lambda: pools.get(pool_id), "running", timeout=600)
    assert pool_at_1.size == 1

    assert_safe_name(name)
    pools.delete(pool_id)
    tracker.unregister(pool_id)


def test_compute_snapshot_lifecycle(tier_3_client, run_id, tracker, tier_3_enabled) -> None:
    """Compute snapshot: create from instance, list, get, export, delete."""
    sg_id, key_name = _make_deps(tier_3_client, run_id, tracker)
    tiny_id = resolve_instance_type(tier_3_client, "standard.tiny")
    template_id = resolve_linux_template(tier_3_client)

    instances = InstanceClient(tier_3_client)
    snapshots = SnapshotClient(tier_3_client)

    payload = _instance_payload(run_id, "snapinst", tiny_id, template_id, sg_id, key_name)
    inst = instances.create(payload)
    inst_id = inst.id
    assert inst_id, "instance create returned no id"
    tracker.register("instance", lambda: instances.delete(inst_id), inst_id)
    wait_for_state(lambda: instances.get(inst_id), "running", timeout=600)

    snap = snapshots.create_from_instance(inst_id)
    snap_id = snap.id
    assert snap_id, "snapshot creation returned no id"
    tracker.register("compute-snapshot", lambda: snapshots.delete(snap_id), snap_id)
    # Snapshotting a live instance settles in state "exported" on current Exoscale
    # (snapshots are auto-exported to object storage); poll for that explicitly.
    terminal = {"exported", "ready"}
    deadline = time.time() + 900
    snap_settled = snapshots.get(snap_id)
    while (snap_settled.state or "").lower() not in terminal and time.time() < deadline:
        time.sleep(10)
        snap_settled = snapshots.get(snap_id)
    assert (snap_settled.state or "").lower() in terminal, (
        f"snapshot never reached a terminal state (last={snap_settled.state})"
    )

    listed = snapshots.list()
    assert any(s.id == snap_id for s in listed)

    # Exercise SnapshotClient.export() against the live API and confirm a
    # presigned download URL comes back. Never print the URL — it grants
    # temporary read access to the exported image. This closes the gap where
    # export() was previously only covered by the mocked unit suite.
    export_op = snapshots.export(snap_id)
    assert (export_op.state or "").lower() == "success", (
        f"snapshot export did not succeed (state={export_op.state})"
    )
    exported = snapshots.get(snap_id)
    assert exported.export is not None and exported.export.presigned_url, (
        "snapshot export produced no presigned URL"
    )

    snapshots.delete(snap_id)
    tracker.unregister(snap_id)

    instances.delete(inst_id)
    tracker.unregister(inst_id)


def test_block_volume_online_lifecycle(tier_3_client, run_id, tracker, tier_3_enabled) -> None:
    """Block volume online ops: attach to instance -> resize -> detach -> delete.

    Block-storage attach requires at least a ``standard.small`` instance — the API
    rejects ``standard.tiny`` with 409 ``Instance size must be at least small``.
    """
    sg_id, key_name = _make_deps(tier_3_client, run_id, tracker)
    # standard.small is the smallest size Exoscale allows for a block-storage host.
    small_id = resolve_instance_type(tier_3_client, "standard.small")
    template_id = resolve_linux_template(tier_3_client)

    instances = InstanceClient(tier_3_client)
    volumes = BlockVolumeClient(tier_3_client)

    payload = _instance_payload(run_id, "volinst", small_id, template_id, sg_id, key_name)
    inst = instances.create(payload)
    inst_id = inst.id
    assert inst_id, "instance create returned no id"
    tracker.register("instance", lambda: instances.delete(inst_id), inst_id)
    wait_for_state(lambda: instances.get(inst_id), "running", timeout=600)

    vol_name = make_name(run_id, "vol-online")
    vol = volumes.create({"name": vol_name, "size": 10})
    vol_id = vol.id
    assert vol_id, "volume create returned no id"

    def _safe_delete_volume() -> None:
        """Detach if still attached, then delete — needed if the test fails mid-way."""
        current = volumes.get(vol_id)
        if (current.state or "").lower() == "attached":
            volumes.detach(vol_id)
            deadline = time.time() + 120
            while time.time() < deadline:
                if (volumes.get(vol_id).state or "").lower() == "detached":
                    break
                time.sleep(3)
        volumes.delete(vol_id)

    tracker.register("block-volume", _safe_delete_volume, vol_id)
    assert vol.state == "detached"

    volumes.attach(vol_id, inst_id)
    attached = wait_for_state(lambda: volumes.get(vol_id), "attached", timeout=300)
    assert (attached.instance.id if attached.instance else None) == inst_id

    # Resize requires sufficient block-storage quota in the tenant; skip the
    # size-change assertions (but still exercise attach/detach) on a quota hit.
    try:
        volumes.resize(vol_id, 20)
    except APIError as exc:
        if exc.status_code == 409 and "block-storage" in str(exc.payload).lower():
            pytest.skip(f"tenant block-storage quota prevents resize: {exc.payload.get('message')}")
        raise

    # Resize on an attached volume usually propagates within a few seconds;
    # poll the size field directly (state stays "attached" through the change).
    deadline = time.time() + 300
    resized = volumes.get(vol_id)
    while resized.size != 20 and time.time() < deadline:
        time.sleep(5)
        resized = volumes.get(vol_id)
    assert resized.size == 20, f"size did not reach 20 (last={resized.size})"

    volumes.detach(vol_id)
    wait_for_state(lambda: volumes.get(vol_id), "detached", timeout=300)

    assert_safe_name(vol_name)
    volumes.delete(vol_id)
    tracker.unregister(vol_id)

    instances.delete(inst_id)
    tracker.unregister(inst_id)


def test_private_network_instance_attach_detach(
    tier_3_client, run_id, tracker, tier_3_enabled
) -> None:
    """Private-network membership: attach an instance, verify, detach, verify gone.

    Exercises PrivateNetworkClient.attach_instance / detach_instance (the
    colon-actions PUT private-network/{id}:attach / :detach). Membership is
    confirmed from the instance side — the instance GET echoes a
    ``private-networks`` list — so this checks the wire effect, not just the
    operation envelope.
    """
    sg_id, key_name = _make_deps(tier_3_client, run_id, tracker)
    tiny_id = resolve_instance_type(tier_3_client, "standard.tiny")
    template_id = resolve_linux_template(tier_3_client)

    instances = InstanceClient(tier_3_client)
    nets = PrivateNetworkClient(tier_3_client)

    # Unmanaged (shared-L2) private network — no DHCP range required.
    net_name = make_name(run_id, "pnet")
    net = nets.create({"name": net_name, "description": "tier-3 attach/detach"})
    net_id = net.id
    assert net_id, "private-network create returned no id"
    tracker.register("private-network", lambda: nets.delete(net_id), net_id)

    payload = _instance_payload(run_id, "pn-inst", tiny_id, template_id, sg_id, key_name)
    inst = instances.create(payload)
    inst_id = inst.id
    assert inst_id, "instance create returned no id"
    tracker.register("instance", lambda: instances.delete(inst_id), inst_id)
    wait_for_state(lambda: instances.get(inst_id), "running", timeout=600)

    def _attached_network_ids() -> list:
        raw = tier_3_client.get(f"instance/{inst_id}")
        return [p.get("id") for p in (raw.get("private-networks") or [])]

    # Attach, then confirm membership surfaces on the instance.
    attach_op = nets.attach_instance(net_id, inst_id)
    assert (attach_op.state or "").lower() == "success", (
        f"attach did not succeed (state={attach_op.state})"
    )
    deadline = time.time() + 120
    while net_id not in _attached_network_ids() and time.time() < deadline:
        time.sleep(5)
    assert net_id in _attached_network_ids(), "network not attached to instance"

    # Detach, then confirm it's gone again.
    detach_op = nets.detach_instance(net_id, inst_id)
    assert (detach_op.state or "").lower() == "success", (
        f"detach did not succeed (state={detach_op.state})"
    )
    deadline = time.time() + 120
    while net_id in _attached_network_ids() and time.time() < deadline:
        time.sleep(5)
    assert net_id not in _attached_network_ids(), "network still attached after detach"

    assert_safe_name(net_name)
    instances.delete(inst_id)
    tracker.unregister(inst_id)
    nets.delete(net_id)
    tracker.unregister(net_id)


def test_instance_scale(tier_3_client, run_id, tracker, tier_3_enabled) -> None:
    """Vertical scaling: create tiny → stop → scale to small → verify (new surface)."""
    from ._fixtures import resolve_instance_type, resolve_linux_template, wait_for_state

    instances = InstanceClient(tier_3_client)
    name = make_name(run_id, "scale-inst")
    assert_safe_name(name)

    tiny = resolve_instance_type(tier_3_client, "standard.tiny")
    small = resolve_instance_type(tier_3_client, "standard.small")
    template = resolve_linux_template(tier_3_client)

    inst = instances.create(
        {
            "name": name,
            "instance-type": {"id": tiny},
            "template": {"id": template},
            "disk-size": 10,
        }
    )
    assert inst.id
    tracker.register("instance", lambda: instances.delete(inst.id), inst.id)
    wait_for_state(lambda: instances.get(inst.id), "running", timeout=600, interval=10)

    instances.stop(inst.id)
    wait_for_state(lambda: instances.get(inst.id), "stopped", timeout=300, interval=5)

    instances.scale(inst.id, small)
    scaled = instances.get(inst.id)
    assert scaled.instance_type is not None and scaled.instance_type.id == small

    instances.delete(inst.id)
    tracker.unregister(inst.id)
