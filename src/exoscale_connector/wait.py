"""State-polling helpers for resources that settle after their operation does.

An async operation completing does not always mean the resource it touched is
usable: an instance create's operation succeeds while the instance is still
``starting``. :func:`wait_for_state` bridges that gap by polling a caller-supplied
getter until the resource reports the expected state.

Example::

    from exoscale_connector.wait import wait_for_state

    inst = instances.create({...})
    inst = wait_for_state(lambda: instances.get(inst.id), "running", timeout=600)
"""

from __future__ import annotations

import time
from typing import Any, Callable, TypeVar

from .errors import WaitTimeoutError

T = TypeVar("T")


def wait_for_state(
    getter: Callable[[], T],
    expected: str,
    *,
    timeout: float = 600.0,
    interval: float = 5.0,
    attr: str = "state",
) -> T:
    """Poll ``getter()`` until its ``attr`` equals ``expected`` (case-insensitive).

    Returns the final object once it reaches the expected state. Raises
    :class:`~exoscale_connector.errors.WaitTimeoutError` if the deadline passes
    first. ``getter`` exceptions propagate immediately — wrap the getter if a
    transient 404 should be tolerated (e.g. right after a create).
    """
    deadline = time.time() + timeout
    last: Any = None
    while time.time() < deadline:
        last = getter()
        if (getattr(last, attr, None) or "").lower() == expected.lower():
            return last
        time.sleep(interval)
    last_state = getattr(last, attr, None)
    raise WaitTimeoutError(
        f"resource never reached state {expected!r} within {timeout}s (last state: {last_state!r})",
        expected=expected,
        last_state=last_state,
    )
