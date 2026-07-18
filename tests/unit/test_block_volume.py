"""Unit tests for the BlockVolumeClient.

All tests use mocked HTTP (``responses`` library) — no real network calls are
made. Covers list, get, find, create (async), delete, attach, detach, resize,
and the create_snapshot helper.
"""

from __future__ import annotations

import json

import responses

from exoscale_connector.resources.block_volume import BlockVolume, BlockVolumeClient


@responses.activate
def test_list_returns_typed_models(client, base_url) -> None:
    responses.add(
        responses.GET,
        f"{base_url}/block-storage",
        json={
            "block-storage-volumes": [
                {"id": "vol-1", "name": "data-vol", "size": 100},
                {"id": "vol-2", "name": "log-vol", "size": 50},
            ]
        },
        status=200,
    )
    vols = BlockVolumeClient(client).list()
    assert len(vols) == 2
    assert [v.name for v in vols] == ["data-vol", "log-vol"]
    assert all(isinstance(v, BlockVolume) for v in vols)


@responses.activate
def test_get_parses_full_fields(client, base_url) -> None:
    responses.add(
        responses.GET,
        f"{base_url}/block-storage/vol-1",
        json={
            "id": "vol-1",
            "name": "data-vol",
            "size": 100,
            "state": "attached",
            "blocksize": 512,
            "created-at": "2024-03-01T00:00:00Z",
            "labels": {"env": "prod"},
            "instance": {"id": "inst-xyz"},
            "snapshots": [{"id": "bsnap-1", "name": "vol-snap"}],
        },
        status=200,
    )
    vol = BlockVolumeClient(client).get("vol-1")
    assert vol.id == "vol-1"
    assert vol.blocksize == 512
    assert vol.labels == {"env": "prod"}
    assert vol.instance is not None and vol.instance.id == "inst-xyz"
    assert vol.snapshots is not None and len(vol.snapshots) == 1
    assert vol.snapshots[0].id == "bsnap-1"


@responses.activate
def test_snapshots_field_reads_block_storage_snapshots_wire_key(client, base_url) -> None:
    """Regression: the live API wraps the volume's snapshots under
    ``block-storage-snapshots`` (not the kebab default ``snapshots``).
    Without the explicit alias on the model field, this list is silently
    dropped to None even when the volume has snapshots.
    """
    responses.add(
        responses.GET,
        f"{base_url}/block-storage/vol-9",
        json={
            "id": "vol-9",
            "name": "with-snaps",
            # WIRE form — the key the real API actually returns.
            "block-storage-snapshots": [
                {"id": "bsnap-a", "name": "snap-a"},
                {"id": "bsnap-b", "name": "snap-b"},
            ],
        },
        status=200,
    )
    vol = BlockVolumeClient(client).get("vol-9")
    assert vol.snapshots is not None
    assert [s.id for s in vol.snapshots] == ["bsnap-a", "bsnap-b"]


@responses.activate
def test_find_by_name(client, base_url) -> None:
    responses.add(
        responses.GET,
        f"{base_url}/block-storage",
        json={"block-storage-volumes": [{"id": "vol-3", "name": "Archive"}]},
        status=200,
    )
    found = BlockVolumeClient(client).find_by_name("archive")
    assert found is not None and found.id == "vol-3"


@responses.activate
def test_create_awaits_operation_and_refetches(client, base_url) -> None:
    responses.add(
        responses.POST,
        f"{base_url}/block-storage",
        json={"id": "op-c1", "state": "success", "reference": {"id": "vol-new"}},
        status=200,
    )
    responses.add(
        responses.GET,
        f"{base_url}/block-storage/vol-new",
        json={"id": "vol-new", "name": "new-vol", "size": 200},
        status=200,
    )
    vol = BlockVolumeClient(client).create({"name": "new-vol", "size": 200})
    assert vol.id == "vol-new"
    assert vol.size == 200


@responses.activate
def test_delete_returns_settled_operation(client, base_url) -> None:
    responses.add(
        responses.DELETE,
        f"{base_url}/block-storage/vol-1",
        json={"id": "op-d1", "state": "pending"},
        status=200,
    )
    responses.add(
        responses.GET,
        f"{base_url}/operation/op-d1",
        json={"id": "op-d1", "state": "success"},
        status=200,
    )
    op = BlockVolumeClient(client).delete("vol-1")
    assert op.state == "success"


@responses.activate
def test_attach_sends_instance_payload(client, base_url) -> None:
    responses.add(
        responses.PUT,
        f"{base_url}/block-storage/vol-1:attach",
        json={"id": "op-att-1", "state": "success"},
        status=200,
    )
    op = BlockVolumeClient(client).attach("vol-1", "inst-xyz")
    assert op.state == "success"
    # Confirm the request body contained the instance reference.
    sent = json.loads(responses.calls[0].request.body)
    assert sent == {"instance": {"id": "inst-xyz"}}


@responses.activate
def test_detach_issues_put_to_correct_path(client, base_url) -> None:
    responses.add(
        responses.PUT,
        f"{base_url}/block-storage/vol-1:detach",
        json={"id": "op-det-1", "state": "success"},
        status=200,
    )
    op = BlockVolumeClient(client).detach("vol-1")
    assert op.state == "success"


@responses.activate
def test_resize_sends_size_payload(client, base_url) -> None:
    # Resize uses the dedicated colon-action endpoint :resize-volume — the plain
    # PUT /block-storage/{id} silently no-ops the size field.
    # The caller passes GiB; the connector converts to bytes on the wire because
    # the live API actually expects bytes despite the OpenAPI documenting GiB.
    responses.add(
        responses.PUT,
        f"{base_url}/block-storage/vol-1:resize-volume",
        json={"id": "op-rsz-1", "state": "success"},
        status=200,
    )
    op = BlockVolumeClient(client).resize("vol-1", 500)
    assert op.state == "success"
    sent = json.loads(responses.calls[0].request.body)
    assert sent["size"] == 500 * 1024 * 1024 * 1024


@responses.activate
def test_create_snapshot_posts_to_volume_action(client, base_url) -> None:
    responses.add(
        responses.POST,
        f"{base_url}/block-storage/vol-1:create-snapshot",
        json={"id": "op-snap-1", "state": "success", "reference": {"id": "bsnap-new"}},
        status=200,
    )
    # The returned object is the settled operation (not a BlockVolume).
    op = BlockVolumeClient(client).create_snapshot("vol-1")
    assert op.state == "success"
    assert op.reference_id == "bsnap-new"
