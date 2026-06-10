"""Unit tests for the low-level HTTP client (mocked transport)."""
from __future__ import annotations

import pytest
import requests
import responses

from exoscale_connector.errors import APIError, NotFoundError, OperationError, OperationTimeoutError


@responses.activate
def test_get_returns_parsed_body(client, base_url) -> None:
    responses.add(responses.GET, f"{base_url}/instance/abc", json={"id": "abc"}, status=200)
    assert client.get("instance/abc") == {"id": "abc"}


@responses.activate
def test_404_raises_not_found(client, base_url) -> None:
    responses.add(
        responses.GET, f"{base_url}/instance/missing", json={"message": "nope"}, status=404
    )
    with pytest.raises(NotFoundError) as excinfo:
        client.get("instance/missing")
    assert excinfo.value.status_code == 404


@responses.activate
def test_non_success_raises_api_error_with_payload(client, base_url) -> None:
    responses.add(responses.POST, f"{base_url}/instance", json={"message": "bad input"}, status=400)
    with pytest.raises(APIError) as excinfo:
        client.post("instance", json={"x": 1})
    assert excinfo.value.status_code == 400
    assert excinfo.value.payload == {"message": "bad input"}


@responses.activate
def test_retries_then_succeeds_on_transient_error(client, base_url) -> None:
    responses.add(responses.GET, f"{base_url}/instance", status=503)
    responses.add(responses.GET, f"{base_url}/instance", json={"instances": []}, status=200)
    assert client.get("instance") == {"instances": []}
    assert len(responses.calls) == 2


@responses.activate
def test_post_is_not_retried_on_500(client, base_url) -> None:
    # A 5xx on a POST is ambiguous — the mutation may have been applied, so a
    # blind retry could create duplicate resources. The error must surface
    # after exactly one attempt.
    responses.add(responses.POST, f"{base_url}/instance", status=500)
    with pytest.raises(APIError) as excinfo:
        client.post("instance", json={"name": "vm-1"})
    assert excinfo.value.status_code == 500
    assert len(responses.calls) == 1


@responses.activate
def test_post_is_retried_on_429(client, base_url) -> None:
    # 429 means the server explicitly did not process the request — safe to retry.
    responses.add(responses.POST, f"{base_url}/instance", status=429)
    responses.add(responses.POST, f"{base_url}/instance", json={"id": "op1"}, status=200)
    assert client.post("instance", json={"name": "vm-1"}) == {"id": "op1"}
    assert len(responses.calls) == 2


@responses.activate
def test_delete_is_retried_on_transient_error(client, base_url) -> None:
    # DELETE is idempotent, so transient 5xx retries remain safe.
    responses.add(responses.DELETE, f"{base_url}/instance/abc", status=502)
    responses.add(
        responses.DELETE, f"{base_url}/instance/abc", json={"id": "op2"}, status=200
    )
    assert client.delete("instance/abc") == {"id": "op2"}
    assert len(responses.calls) == 2


@responses.activate
def test_wait_operation_polls_until_success(client, base_url) -> None:
    responses.add(
        responses.GET,
        f"{base_url}/operation/op1",
        json={"id": "op1", "state": "pending"},
        status=200,
    )
    responses.add(
        responses.GET,
        f"{base_url}/operation/op1",
        json={"id": "op1", "state": "success", "reference": {"id": "res1"}},
        status=200,
    )
    op = client.wait_operation("op1", poll_interval=0)
    assert op.state == "success"
    assert op.reference_id == "res1"


@responses.activate
def test_wait_operation_raises_on_failure(client, base_url) -> None:
    responses.add(
        responses.GET,
        f"{base_url}/operation/op2",
        json={"id": "op2", "state": "failure", "reason": "quota"},
        status=200,
    )
    with pytest.raises(OperationError):
        client.wait_operation("op2", poll_interval=0)


@responses.activate
def test_wait_operation_times_out(client, base_url) -> None:
    responses.add(
        responses.GET,
        f"{base_url}/operation/op3",
        json={"id": "op3", "state": "pending"},
        status=200,
    )
    with pytest.raises(OperationTimeoutError):
        client.wait_operation("op3", timeout=0, poll_interval=0)


@responses.activate
def test_wait_operation_tolerates_transient_connection_drops(client, base_url) -> None:
    # Two connection drops in a row, then the operation reports success.
    responses.add(
        responses.GET, f"{base_url}/operation/op4", body=requests.exceptions.ConnectionError("drop")
    )
    responses.add(
        responses.GET, f"{base_url}/operation/op4", body=requests.exceptions.ConnectionError("drop")
    )
    responses.add(
        responses.GET,
        f"{base_url}/operation/op4",
        json={"id": "op4", "state": "success"},
        status=200,
    )
    op = client.wait_operation("op4", poll_interval=0)
    assert op.state == "success"


@responses.activate
def test_wait_operation_tolerates_sporadic_404(client, base_url) -> None:
    # The operation resource can 404 briefly while it is still propagating.
    responses.add(
        responses.GET, f"{base_url}/operation/op5", json={"message": "not yet"}, status=404
    )
    responses.add(
        responses.GET,
        f"{base_url}/operation/op5",
        json={"id": "op5", "state": "success"},
        status=200,
    )
    op = client.wait_operation("op5", poll_interval=0)
    assert op.state == "success"


@responses.activate
def test_wait_operation_surfaces_after_too_many_poll_failures(client, base_url) -> None:
    # config.max_poll_failures defaults to 3, so the 4th consecutive drop surfaces.
    responses.add(
        responses.GET, f"{base_url}/operation/op6", body=requests.exceptions.ConnectionError("drop")
    )
    with pytest.raises(requests.exceptions.ConnectionError):
        client.wait_operation("op6", poll_interval=0)
    assert len(responses.calls) == client.config.max_poll_failures + 1


@responses.activate
def test_wait_operation_resets_failure_counter_on_success(client, base_url) -> None:
    # Two drops, a good (pending) poll that resets the counter, then three more
    # drops (still within the per-run budget) before success. Without the reset
    # the cumulative five failures would surface instead.
    drop = requests.exceptions.ConnectionError("drop")
    for body in (drop, drop):
        responses.add(responses.GET, f"{base_url}/operation/op7", body=body)
    responses.add(
        responses.GET,
        f"{base_url}/operation/op7",
        json={"id": "op7", "state": "pending"},
        status=200,
    )
    for body in (drop, drop, drop):
        responses.add(responses.GET, f"{base_url}/operation/op7", body=body)
    responses.add(
        responses.GET,
        f"{base_url}/operation/op7",
        json={"id": "op7", "state": "success"},
        status=200,
    )
    op = client.wait_operation("op7", poll_interval=0)
    assert op.state == "success"
