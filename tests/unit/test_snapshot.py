"""Unit tests for the SnapshotClient.

All tests use mocked HTTP (``responses`` library) — no real network calls are
made. The pattern mirrors test_security_group.py: list, find, get, delete, plus
the snapshot-specific create_from_instance and export helpers.
"""

from __future__ import annotations

import responses

from exoscale_connector.resources.snapshot import Snapshot, SnapshotClient


@responses.activate
def test_list_returns_typed_models(client, base_url) -> None:
    responses.add(
        responses.GET,
        f"{base_url}/snapshot",
        json={
            "snapshots": [
                {"id": "snap-1", "name": "daily-backup", "state": "exported"},
                {"id": "snap-2", "name": "pre-upgrade", "state": "ready"},
            ]
        },
        status=200,
    )
    snaps = SnapshotClient(client).list()
    assert len(snaps) == 2
    assert [s.name for s in snaps] == ["daily-backup", "pre-upgrade"]
    assert all(isinstance(s, Snapshot) for s in snaps)


@responses.activate
def test_get_parses_all_fields(client, base_url) -> None:
    responses.add(
        responses.GET,
        f"{base_url}/snapshot/snap-1",
        json={
            "id": "snap-1",
            "name": "daily-backup",
            "size": 50,
            "state": "ready",
            "created-at": "2024-01-15T10:30:00Z",
            "instance": {"id": "inst-abc"},
        },
        status=200,
    )
    snap = SnapshotClient(client).get("snap-1")
    assert snap.id == "snap-1"
    assert snap.size == 50
    assert snap.state == "ready"
    assert snap.instance is not None
    assert snap.instance.id == "inst-abc"
    # kebab-case alias must deserialise correctly
    assert snap.created_at == "2024-01-15T10:30:00Z"


@responses.activate
def test_find_by_name_case_insensitive(client, base_url) -> None:
    responses.add(
        responses.GET,
        f"{base_url}/snapshot",
        json={"snapshots": [{"id": "snap-3", "name": "MySnap"}]},
        status=200,
    )
    found = SnapshotClient(client).find_by_name("mysnap")
    assert found is not None
    assert found.id == "snap-3"


@responses.activate
def test_find_by_name_returns_none_when_absent(client, base_url) -> None:
    responses.add(
        responses.GET,
        f"{base_url}/snapshot",
        json={"snapshots": []},
        status=200,
    )
    assert SnapshotClient(client).find_by_name("ghost") is None


@responses.activate
def test_delete_awaits_operation(client, base_url) -> None:
    responses.add(
        responses.DELETE,
        f"{base_url}/snapshot/snap-1",
        json={"id": "op-del-1", "state": "pending"},
        status=200,
    )
    responses.add(
        responses.GET,
        f"{base_url}/operation/op-del-1",
        json={"id": "op-del-1", "state": "success"},
        status=200,
    )
    op = SnapshotClient(client).delete("snap-1")
    assert op.state == "success"


@responses.activate
def test_create_from_instance_returns_new_snapshot(client, base_url) -> None:
    # The instance action returns an async operation referencing the new snapshot.
    responses.add(
        responses.POST,
        f"{base_url}/instance/inst-abc:create-snapshot",
        json={"id": "op-cs-1", "state": "success", "reference": {"id": "snap-new"}},
        status=200,
    )
    # The client re-fetches the snapshot after the operation settles.
    responses.add(
        responses.GET,
        f"{base_url}/snapshot/snap-new",
        json={"id": "snap-new", "name": "auto-snap", "state": "ready"},
        status=200,
    )
    snap = SnapshotClient(client).create_from_instance("inst-abc")
    assert snap.id == "snap-new"
    assert snap.name == "auto-snap"


@responses.activate
def test_export_returns_operation(client, base_url) -> None:
    responses.add(
        responses.POST,
        f"{base_url}/snapshot/snap-1:export",
        json={"id": "op-exp-1", "state": "pending"},
        status=200,
    )
    responses.add(
        responses.GET,
        f"{base_url}/operation/op-exp-1",
        json={"id": "op-exp-1", "state": "success"},
        status=200,
    )
    op = SnapshotClient(client).export("snap-1")
    assert op.state == "success"
    assert op.id == "op-exp-1"


@responses.activate
def test_export_no_wait_returns_pending(client, base_url) -> None:
    """With wait=False the operation is returned immediately without polling."""
    responses.add(
        responses.POST,
        f"{base_url}/snapshot/snap-1:export",
        json={"id": "op-exp-2", "state": "pending"},
        status=200,
    )
    op = SnapshotClient(client).export("snap-1", wait=False)
    assert op.state == "pending"
    # No poll call should have been made.
    assert len(responses.calls) == 1
