"""Tier 2 live tests — cheap, non-compute asset types.

Enabled by:

    EXOSCALE_ALLOW_MUTATION=1
    EXOSCALE_TEST_TIER_2=1
    EXOSCALE_RUN_LIVE_TESTS=1
    EXOSCALE_API_KEY / EXOSCALE_API_SECRET / EXOSCALE_TEST_ZONE

Covers elastic-ip, object-storage bucket (S3, via boto3) and the detached
block-volume lifecycle including resize and snapshot. Attach/detach require an
instance and are covered in Tier 3, not here. All resources carry the
``conn-test-`` prefix and are cleaned up by the tracker on teardown.
"""
from __future__ import annotations

import secrets
import string

import pytest

from exoscale_connector.resources.block_volume import BlockVolumeClient
from exoscale_connector.resources.block_volume_snapshot import BlockVolumeSnapshotClient
from exoscale_connector.resources.elastic_ip import ElasticIPClient

from ._fixtures import assert_safe_name, make_name

pytestmark = pytest.mark.integration


def test_elastic_ip_lifecycle(live_client, run_id, tracker, tier_2_enabled) -> None:
    """Elastic IP: create + get + update description + delete.

    EIPs are charged while allocated; the test allocates one for a few seconds.
    """
    eip = ElasticIPClient(live_client)
    description = make_name(run_id, "eip")
    created = eip.create({"description": description, "addressfamily": "inet4"})
    eip_id = created.id
    assert eip_id, "create did not return an id"
    tracker.register("elastic-ip", lambda: eip.delete(eip_id), eip_id)

    fetched = eip.get(eip_id)
    assert fetched.description == description
    assert fetched.ip, "the API did not assign an IP"

    new_desc = description + "-updated"
    eip.update(eip_id, {"description": new_desc})
    after = eip.get(eip_id)
    assert after.description == new_desc

    # EIP description is the only field that carries our prefix; assert before deleting.
    assert_safe_name(description)
    eip.delete(eip_id)
    tracker.unregister(eip_id)


def test_bucket_lifecycle(live_client, run_id, tracker, tier_2_enabled) -> None:
    """Object-storage bucket: create + exists + list + delete (S3, via boto3)."""
    pytest.importorskip("boto3")
    from exoscale_connector.resources.object_storage import BucketClient

    # Bucket names must be 3–63 chars, lowercase, no underscores, globally unique.
    suffix = "".join(secrets.choice(string.ascii_lowercase + string.digits) for _ in range(16))
    name = (make_name(run_id, "bucket") + "-" + suffix).lower()[:63]
    buckets = BucketClient(live_client.config)
    buckets.create(name)
    tracker.register("bucket", lambda: buckets.delete(name), name)

    assert buckets.exists(name)
    listed = buckets.list()
    assert any(b.name == name for b in listed), f"freshly created bucket {name!r} not in list"

    assert_safe_name(name)
    buckets.delete(name)
    tracker.unregister(name)
    assert not buckets.exists(name)


def test_block_volume_lifecycle(live_client, run_id, tracker, tier_2_enabled) -> None:
    """Detached block-volume + snapshot lifecycle: create → snapshot → delete.

    Resize is an online operation: the volume must be attached to a running
    instance for the size change to actually propagate, so it lives in Tier 3
    where instance fixtures are available. Same for attach/detach.
    """
    volumes = BlockVolumeClient(live_client)
    snapshots = BlockVolumeSnapshotClient(live_client)

    name = make_name(run_id, "vol")
    # Smallest typical block-storage volume in the API is 10 GiB.
    created = volumes.create({"name": name, "size": 10})
    vol_id = created.id
    assert vol_id, "create did not return an id"
    tracker.register("block-volume", lambda: volumes.delete(vol_id), vol_id)

    fetched = volumes.get(vol_id)
    assert fetched.name == name
    assert fetched.size == 10
    assert fetched.state == "detached"

    found = volumes.find_by_name(name)
    assert found is not None and found.id == vol_id

    # Snapshot the volume (action endpoint; returns an operation whose reference
    # points at the new snapshot).
    snap_op = volumes.create_snapshot(vol_id)
    snap_id = snap_op.reference_id
    assert snap_id, "create-snapshot operation had no reference id"
    tracker.register("block-volume-snapshot", lambda: snapshots.delete(snap_id), snap_id)
    snap = snapshots.get(snap_id)
    assert snap.id == snap_id

    # Snapshots must be deleted before the parent volume.
    snapshots.delete(snap_id)
    tracker.unregister(snap_id)

    assert_safe_name(name)
    volumes.delete(vol_id)
    tracker.unregister(vol_id)
