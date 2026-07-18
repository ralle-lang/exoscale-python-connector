"""Unit tests for the BlockVolumeSnapshotClient.

All tests use mocked HTTP (``responses`` library) — no real network calls are
made. Covers list, get, find, delete, update, and the create_from_volume helper.
"""

from __future__ import annotations

import responses

from exoscale_connector.resources.block_volume_snapshot import (
    BlockVolumeSnapshot,
    BlockVolumeSnapshotClient,
)


@responses.activate
def test_list_returns_typed_models(client, base_url) -> None:
    responses.add(
        responses.GET,
        f"{base_url}/block-storage-snapshot",
        json={
            "block-storage-snapshots": [
                {"id": "bsnap-1", "name": "vol-snap-daily"},
                {"id": "bsnap-2", "name": "vol-snap-weekly"},
            ]
        },
        status=200,
    )
    snaps = BlockVolumeSnapshotClient(client).list()
    assert len(snaps) == 2
    assert [s.name for s in snaps] == ["vol-snap-daily", "vol-snap-weekly"]
    assert all(isinstance(s, BlockVolumeSnapshot) for s in snaps)


@responses.activate
def test_get_parses_all_fields(client, base_url) -> None:
    responses.add(
        responses.GET,
        f"{base_url}/block-storage-snapshot/bsnap-1",
        json={
            "id": "bsnap-1",
            "name": "vol-snap-daily",
            "size": 100,
            "state": "created",
            "created-at": "2024-05-01T06:00:00Z",
            "labels": {"tier": "gold"},
        },
        status=200,
    )
    snap = BlockVolumeSnapshotClient(client).get("bsnap-1")
    assert snap.id == "bsnap-1"
    assert snap.size == 100
    assert snap.state == "created"
    assert snap.labels == {"tier": "gold"}
    assert snap.created_at == "2024-05-01T06:00:00Z"


@responses.activate
def test_find_by_name_case_insensitive(client, base_url) -> None:
    responses.add(
        responses.GET,
        f"{base_url}/block-storage-snapshot",
        json={"block-storage-snapshots": [{"id": "bsnap-3", "name": "MyVolumeSnap"}]},
        status=200,
    )
    found = BlockVolumeSnapshotClient(client).find_by_name("myvolumesnap")
    assert found is not None and found.id == "bsnap-3"


@responses.activate
def test_find_by_name_returns_none_when_absent(client, base_url) -> None:
    responses.add(
        responses.GET,
        f"{base_url}/block-storage-snapshot",
        json={"block-storage-snapshots": []},
        status=200,
    )
    assert BlockVolumeSnapshotClient(client).find_by_name("missing") is None


@responses.activate
def test_delete_awaits_operation(client, base_url) -> None:
    responses.add(
        responses.DELETE,
        f"{base_url}/block-storage-snapshot/bsnap-1",
        json={"id": "op-del-bs-1", "state": "pending"},
        status=200,
    )
    responses.add(
        responses.GET,
        f"{base_url}/operation/op-del-bs-1",
        json={"id": "op-del-bs-1", "state": "success"},
        status=200,
    )
    op = BlockVolumeSnapshotClient(client).delete("bsnap-1")
    assert op.state == "success"


@responses.activate
def test_update_puts_and_refetches(client, base_url) -> None:
    responses.add(
        responses.PUT,
        f"{base_url}/block-storage-snapshot/bsnap-1",
        json={"id": "op-upd-bs-1", "state": "success", "reference": {"id": "bsnap-1"}},
        status=200,
    )
    responses.add(
        responses.GET,
        f"{base_url}/block-storage-snapshot/bsnap-1",
        json={"id": "bsnap-1", "name": "renamed-snap", "size": 100, "state": "created"},
        status=200,
    )
    snap = BlockVolumeSnapshotClient(client).update("bsnap-1", {"name": "renamed-snap"})
    assert snap.id == "bsnap-1"
    assert snap.name == "renamed-snap"


@responses.activate
def test_create_from_volume_returns_new_snapshot(client, base_url) -> None:
    # Volume action returns an async operation referencing the new snapshot.
    responses.add(
        responses.POST,
        f"{base_url}/block-storage/vol-abc:create-snapshot",
        json={"id": "op-cs-bs-1", "state": "success", "reference": {"id": "bsnap-new"}},
        status=200,
    )
    # The client re-fetches the snapshot after the operation settles.
    responses.add(
        responses.GET,
        f"{base_url}/block-storage-snapshot/bsnap-new",
        json={"id": "bsnap-new", "name": "new-volume-snap", "state": "created"},
        status=200,
    )
    snap = BlockVolumeSnapshotClient(client).create_from_volume("vol-abc")
    assert snap.id == "bsnap-new"
    assert snap.name == "new-volume-snap"


@responses.activate
def test_create_from_volume_no_wait(client, base_url) -> None:
    """With wait=False the operation is returned without polling or re-fetching."""
    responses.add(
        responses.POST,
        f"{base_url}/block-storage/vol-abc:create-snapshot",
        json={"id": "op-cs-bs-2", "state": "pending"},
        status=200,
    )
    # create_from_volume delegates to _resolve_mutation; with wait=False and a
    # settled-looking (no reference) operation, it returns the model directly.
    # The important assertion is that only one HTTP call was made.
    BlockVolumeSnapshotClient(client).create_from_volume("vol-abc", wait=False)
    assert len(responses.calls) == 1
