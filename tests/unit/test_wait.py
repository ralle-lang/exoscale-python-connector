"""Unit tests for the wait_for_state helper."""

from __future__ import annotations

import pytest

from exoscale_connector.errors import WaitTimeoutError
from exoscale_connector.wait import wait_for_state


class _Thing:
    def __init__(self, state):
        self.state = state


def test_returns_once_state_matches() -> None:
    states = iter(["starting", "starting", "Running"])

    result = wait_for_state(lambda: _Thing(next(states)), "running", timeout=5, interval=0)
    assert result.state == "Running"  # case-insensitive match, original object returned


def test_raises_wait_timeout_with_last_state() -> None:
    with pytest.raises(WaitTimeoutError) as excinfo:
        wait_for_state(lambda: _Thing("stuck"), "running", timeout=0, interval=0)
    assert excinfo.value.expected == "running"
    # timeout=0 means the loop body never runs; last observed state is None.
    assert excinfo.value.last_state is None


def test_custom_attribute() -> None:
    class Pool:
        status = "ready"

    pool = Pool()
    assert wait_for_state(lambda: pool, "ready", timeout=5, interval=0, attr="status") is pool


def test_getter_exceptions_propagate() -> None:
    def boom():
        raise RuntimeError("fetch failed")

    with pytest.raises(RuntimeError):
        wait_for_state(boom, "running", timeout=5, interval=0)
