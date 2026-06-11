"""Gating for the opt-in live integration tests.

These tests talk to a real Exoscale account and are skipped unless explicitly
enabled. Enable them by setting, in the environment:

    EXOSCALE_RUN_LIVE_TESTS=1      # master switch
    EXOSCALE_API_KEY / EXOSCALE_API_SECRET
    EXOSCALE_TEST_ZONE=<zone>      # which zone to exercise

The default integration suite is strictly read-only, so it is safe against any
account. Any test that *mutates* resources must additionally be guarded by your
own allowlist (see the ``require_mutation_allowed`` fixture) so a real
environment is never modified by accident.
"""
from __future__ import annotations

import os

import pytest

from exoscale_connector.client import ExoscaleClient
from exoscale_connector.config import ClientConfig


def _live_enabled() -> bool:
    value = os.environ.get("EXOSCALE_RUN_LIVE_TESTS", "").strip().lower()
    return value in {"1", "true", "yes", "on"}


@pytest.fixture(scope="session")
def live_client() -> ExoscaleClient:
    """A real client built from the environment, or skip the whole live suite."""
    if not _live_enabled():
        pytest.skip("live tests disabled (set EXOSCALE_RUN_LIVE_TESTS=1 to enable)")
    zone = os.environ.get("EXOSCALE_TEST_ZONE", "").strip()
    if not zone:
        pytest.skip("EXOSCALE_TEST_ZONE not set")
    try:
        config = ClientConfig.from_env(zone=zone)
    except Exception as exc:  # missing creds -> skip rather than error
        pytest.skip(f"live credentials unavailable: {exc}")
    client = ExoscaleClient(config)
    if _env_bool("EXOSCALE_RECORD"):
        # Capture sanitized wire shapes for the offline replay suite.
        # Review recordings before committing them (see _recorder.py).
        from ._fixtures import make_run_id
        from ._recorder import RECORDINGS_DIR, attach_recorder

        attach_recorder(client._session, RECORDINGS_DIR / f"live-{make_run_id()}.jsonl")
    return client


def _env_bool(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


@pytest.fixture
def require_mutation_allowed() -> None:
    """Hard gate for tests that create/modify/delete real resources.

    Mutating tests must opt in explicitly via ``EXOSCALE_ALLOW_MUTATION=1``. This
    is deliberately a separate switch from the master one so read-only runs can
    never accidentally change a live environment. Configure the allowlist for your
    own setup — the connector ships no environment-specific defaults.
    """
    if not _env_bool("EXOSCALE_ALLOW_MUTATION"):
        pytest.skip("mutating live tests disabled (set EXOSCALE_ALLOW_MUTATION=1 to enable)")


@pytest.fixture
def tier_1_enabled(require_mutation_allowed) -> None:
    """Gate Tier 1 mutating tests behind their own opt-in switch.

    Tier 1 covers the free, non-compute asset types (security-group,
    private-network, anti-affinity-group, ssh-key, iam-role, dns).
    """
    if not _env_bool("EXOSCALE_TEST_TIER_1"):
        pytest.skip("Tier 1 live tests disabled (set EXOSCALE_TEST_TIER_1=1 to enable)")


@pytest.fixture
def tier_1_api_key_enabled(tier_1_enabled) -> None:
    """Gate the api-key sub-test of Tier 1 separately.

    The create response carries a single-shot secret; even with the test
    asserting non-empty without printing, we keep this off by default so
    a casual Tier 1 run never produces a secret-bearing response.
    """
    if not _env_bool("EXOSCALE_TEST_TIER_1_API_KEY"):
        pytest.skip(
            "api-key live test disabled (set EXOSCALE_TEST_TIER_1_API_KEY=1 to enable)"
        )


@pytest.fixture
def template_register_enabled(tier_1_enabled):
    """Gate the template register/delete sub-test of Tier 1 separately.

    Requires EXOSCALE_TEST_TEMPLATE_URL pointing to a publicly accessible
    qcow2 image and EXOSCALE_TEST_TEMPLATE_CHECKSUM with its MD5 digest.
    Skipped by default so a normal Tier 1 run does not attempt to import
    a disk image (slow, tenant-quota dependent).
    """
    url = os.environ.get("EXOSCALE_TEST_TEMPLATE_URL", "").strip()
    checksum = os.environ.get("EXOSCALE_TEST_TEMPLATE_CHECKSUM", "").strip()
    if not url or not checksum:
        pytest.skip(
            "template register/delete test disabled "
            "(set EXOSCALE_TEST_TEMPLATE_URL and EXOSCALE_TEST_TEMPLATE_CHECKSUM to enable)"
        )
    return url, checksum


@pytest.fixture
def tier_2_enabled(require_mutation_allowed) -> None:
    """Gate Tier 2 mutating tests behind their own opt-in switch.

    Tier 2 covers cheap, non-compute asset types: elastic-ip, object-storage
    bucket (S3, via boto3), and detached block-volume operations.
    """
    if not _env_bool("EXOSCALE_TEST_TIER_2"):
        pytest.skip("Tier 2 live tests disabled (set EXOSCALE_TEST_TIER_2=1 to enable)")


@pytest.fixture
def tier_3_enabled(require_mutation_allowed) -> None:
    """Gate Tier 3 mutating tests behind their own opt-in switch.

    Tier 3 spins up the smallest possible compute resources: instance(+lifecycle),
    instance-pool(+scale), compute snapshot from an instance, and block-volume
    online operations (attach/resize/detach) that require an attached instance.
    """
    if not _env_bool("EXOSCALE_TEST_TIER_3"):
        pytest.skip("Tier 3 live tests disabled (set EXOSCALE_TEST_TIER_3=1 to enable)")


@pytest.fixture
def tier_4_lb_enabled(require_mutation_allowed) -> None:
    """Tier 4 — load-balancer (creates its own backing instance-pool)."""
    if not _env_bool("EXOSCALE_TEST_TIER_4_LB"):
        pytest.skip("Tier 4 LB tests disabled (set EXOSCALE_TEST_TIER_4_LB=1 to enable)")


@pytest.fixture
def tier_4_dbaas_enabled(require_mutation_allowed) -> None:
    """Tier 4 — DBaaS (cheapest pg plan; 5–15 min provisioning)."""
    if not _env_bool("EXOSCALE_TEST_TIER_4_DBAAS"):
        pytest.skip("Tier 4 DBaaS tests disabled (set EXOSCALE_TEST_TIER_4_DBAAS=1 to enable)")


@pytest.fixture
def tier_4_sks_enabled(require_mutation_allowed) -> None:
    """Tier 4 — SKS cluster + nodepool + kubeconfig (longest-running tier)."""
    if not _env_bool("EXOSCALE_TEST_TIER_4_SKS"):
        pytest.skip("Tier 4 SKS tests disabled (set EXOSCALE_TEST_TIER_4_SKS=1 to enable)")


@pytest.fixture
def tier_3_client(live_client):
    """A client with an extended timeout suitable for instance provisioning.

    The default 60-second timeout is fine for control-plane operations but tight
    for instance create / snapshot ops, which can take several minutes for the
    operation status to flip to ``success``.
    """
    from exoscale_connector.client import ExoscaleClient
    from exoscale_connector.config import ClientConfig

    base = live_client.config
    extended = ClientConfig(
        api_key=base.api_key,
        api_secret=base.api_secret,
        zone=base.zone,
        endpoint=base.endpoint,
        timeout=600.0,  # 10 min — long enough for any single async op to settle
        verify_tls=base.verify_tls,
        max_retries=base.max_retries,
        retry_backoff=base.retry_backoff,
    )
    client = ExoscaleClient(extended)
    if _env_bool("EXOSCALE_RECORD"):
        # This is a fresh session — the recorder attached to live_client does
        # not carry over. Without this, tier 3/4 runs record nothing.
        from ._fixtures import make_run_id
        from ._recorder import RECORDINGS_DIR, attach_recorder

        attach_recorder(client._session, RECORDINGS_DIR / f"live-{make_run_id()}.jsonl")
    return client


@pytest.fixture
def run_id() -> str:
    """A unique, lowercase, DNS-label-safe id for the current test."""
    from ._fixtures import make_run_id

    return make_run_id()


@pytest.fixture
def tracker():
    """Per-test resource tracker that sweeps anything still registered on teardown."""
    from ._fixtures import ResourceTracker

    tracker_obj = ResourceTracker()
    yield tracker_obj
    results = tracker_obj.sweep()
    # Surface the sweep outcome so a failed test still reports what it leaked.
    for label, resource_id, status in results:
        print(f"\n[teardown] {label}/{resource_id}: {status}")
