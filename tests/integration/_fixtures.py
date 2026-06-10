"""Helpers shared by the live-test tiers.

The tests in this directory mutate a real Exoscale account, so every resource
they create carries a uniquely-prefixed name and is recorded in a per-session
:class:`ResourceTracker`. The tracker guarantees cleanup even if a test crashes
between provision and explicit delete.

Two non-negotiable invariants are enforced here:

1. Every created resource's name starts with ``EXOSCALE_TEST_PREFIX`` (default
   ``conn-test``). :func:`assert_safe_name` raises if that is ever not the case.
2. Cleanup runs from the tracker's registry, not from a live ``list()``. A wild
   ``list()`` could match an unrelated resource in the shared tenant; the
   registry path cannot.
"""
from __future__ import annotations

import os
import secrets
import string
import time
from dataclasses import dataclass, field
from typing import Any, Callable, List, Optional, Tuple

# Discriminator every test resource must carry. Configurable so users can run
# parallel test sets without collision, but immutable per run.
TEST_PREFIX = os.environ.get("EXOSCALE_TEST_PREFIX", "conn-test").strip() or "conn-test"


def make_run_id() -> str:
    """Build a session-unique id: UTC timestamp + 6 random lowercase chars."""
    # Lowercase to keep DNS labels valid (RFC 1035 allows only [a-z0-9-]).
    ts = time.strftime("%Y%m%dt%H%M%Sz", time.gmtime())
    rand = "".join(secrets.choice(string.ascii_lowercase + string.digits) for _ in range(6))
    return f"{ts}-{rand}"


def make_name(run_id: str, suffix: str) -> str:
    """Compose a test-resource name; capped at 120 chars to satisfy API limits."""
    return f"{TEST_PREFIX}-{run_id}-{suffix}"[:120]


def assert_safe_name(name: str) -> None:
    """Refuse to act on any resource whose name doesn't carry the test prefix."""
    if not name or not name.startswith(TEST_PREFIX):
        raise AssertionError(
            f"Refusing to act on resource {name!r}: does not start with {TEST_PREFIX!r}. "
            "Tests must never touch resources they did not create."
        )


@dataclass
class ResourceTracker:
    """Per-test registry of created resources, with guaranteed teardown sweep.

    Each registered entry stores a ``deleter`` thunk that knows how to delete
    that specific resource (some resources need a parent id, so a thunk is more
    robust than (client, id) pairs).
    """

    items: List[Tuple[str, Callable[[], None], str]] = field(default_factory=list)

    def register(self, label: str, deleter: Callable[[], None], resource_id: str) -> None:
        self.items.append((label, deleter, resource_id))

    def unregister(self, resource_id: str) -> None:
        """Drop an id after a clean explicit delete; what remains is post-failure leakage."""
        self.items = [item for item in self.items if item[2] != resource_id]

    def sweep(self) -> List[Tuple[str, str, str]]:
        """Delete any still-registered resources in reverse-creation order.

        Returns a list of ``(label, id, status)`` tuples so the teardown phase can
        report what was cleaned up and what failed.
        """
        results: List[Tuple[str, str, str]] = []
        for label, deleter, resource_id in reversed(self.items):
            try:
                deleter()
                results.append((label, resource_id, "swept"))
            except Exception as exc:  # noqa: BLE001  — sweep must not raise
                results.append(
                    (label, resource_id, f"sweep-failed: {type(exc).__name__}: {exc}")
                )
        self.items.clear()
        return results


# ---------------------------------------------------------------------------- #
# Compute helpers (used by Tier 3+)
# ---------------------------------------------------------------------------- #


def resolve_instance_type(
    client: Any, name: str = "standard.tiny", zone: Optional[str] = None
) -> str:
    """Look up an instance-type id by its ``family.size`` name (e.g. ``standard.tiny``)."""
    payload = client.get("instance-type", zone=zone)
    for item in payload.get("instance-types", []):
        if not isinstance(item, dict):
            continue
        family = (item.get("family") or "").lower()
        size = (item.get("size") or "").lower()
        if f"{family}.{size}" == name.lower():
            return str(item["id"])
    raise RuntimeError(f"instance-type {name!r} not available in this zone")


def resolve_linux_template(client: Any, zone: Optional[str] = None) -> str:
    """Pick the smallest public Linux template available in the zone.

    Tests don't care about the specific OS, only that the template boots; we
    sort by ``size`` (the minimum disk size the template needs) so the test
    instance has the smallest possible footprint.
    """
    payload = client.get("template", zone=zone, params={"visibility": "public"})
    templates = [
        t
        for t in payload.get("templates", [])
        if isinstance(t, dict) and "linux" in (t.get("family") or "").lower()
    ]
    if not templates:
        raise RuntimeError("no public Linux template available")
    templates.sort(key=lambda t: t.get("size") or float("inf"))
    return str(templates[0]["id"])


def resolve_cheapest_dbaas_plan(
    client: Any, service_type: str = "pg", zone: Optional[str] = None
) -> str:
    """Look up the cheapest plan name for a DBaaS service type.

    Sorts the plan list by ``disk-space`` (proxy for cost) and returns the
    smallest. Tests pick a plan dynamically so they don't pin a price tier
    that may be removed by Exoscale.
    """
    payload = client.get(f"dbaas-service-type/{service_type}", zone=zone)
    plans = [p for p in payload.get("plans", []) if isinstance(p, dict)]
    if not plans:
        raise RuntimeError(f"no DBaaS plans available for service type {service_type!r}")
    plans.sort(key=lambda p: (p.get("disk-space") or float("inf"), p.get("nodes") or float("inf")))
    return str(plans[0]["name"])


def resolve_sks_version(client: Any, zone: Optional[str] = None) -> str:
    """Pick a currently-supported SKS cluster version (the lowest exposed).

    Exoscale's SKS API returns supported versions in
    ``GET /sks-cluster-version``; we pick the smallest stable one so the test
    doesn't fight upgrades. Returns the version string (e.g. ``"1.30.5"``).
    """
    payload = client.get("sks-cluster-version", zone=zone)
    versions = payload.get("sks-cluster-versions") or payload.get("versions") or []
    versions = [str(v) for v in versions if v]
    if not versions:
        raise RuntimeError("no SKS cluster versions exposed by the API")
    # Versions are typically already sorted; sort defensively as strings split on dots.
    versions.sort(key=lambda v: tuple(int(part) for part in v.split(".") if part.isdigit()))
    return versions[0]


# wait_for_state graduated into the library (it was always user-facing — the
# asset-type docs reference it). Re-exported here so the tiers keep importing
# it from _fixtures. It now raises WaitTimeoutError instead of AssertionError.
from exoscale_connector.wait import wait_for_state  # noqa: E402,F401
