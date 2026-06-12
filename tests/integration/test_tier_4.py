"""Tier 4 live tests — expensive / long-lived managed services.

Each of the three subtiers is gated by its own env flag so they can be enabled
independently:

    EXOSCALE_TEST_TIER_4_LB=1      # load-balancer + service (creates its own pool)
    EXOSCALE_TEST_TIER_4_DBAAS=1   # DBaaS (cheapest pg plan; 5-15 min provisioning)
    EXOSCALE_TEST_TIER_4_SKS=1     # SKS cluster + nodepool + kubeconfig

Every Tier 4 test also requires the master mutation switch
``EXOSCALE_ALLOW_MUTATION=1`` and ``EXOSCALE_RUN_LIVE_TESTS=1``.

All resources carry the conn-test- prefix and are tracked for guaranteed
teardown. Secret-bearing responses (DBaaS connection info, password reveal,
SKS kubeconfig) are asserted present but never printed.
"""
from __future__ import annotations

import time

import pytest

from exoscale_connector.resources.dbaas import DBaaSServiceClient
from exoscale_connector.resources.instance_pool import InstancePoolClient
from exoscale_connector.resources.load_balancer import LoadBalancerClient
from exoscale_connector.resources.sks import SksClusterClient, SksNodepool

from ._fixtures import (
    assert_safe_name,
    make_name,
    resolve_cheapest_dbaas_plan,
    resolve_instance_type,
    resolve_linux_template,
    resolve_sks_version,
    wait_for_state,
)

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------- #
# Load balancer
# ---------------------------------------------------------------------------- #


def test_load_balancer_lifecycle(tier_3_client, run_id, tracker, tier_4_lb_enabled) -> None:
    """Load balancer + service: create LB → add service → update → delete service → delete LB.

    Service requires a backing instance-pool. The test creates a tiny pool of
    size 1, points the service at it, then cleans up everything in reverse
    order (service → LB → pool).
    """
    pools = InstancePoolClient(tier_3_client)
    lbs = LoadBalancerClient(tier_3_client)
    tiny_id = resolve_instance_type(tier_3_client, "standard.tiny")
    template_id = resolve_linux_template(tier_3_client)

    # 1. Backing pool — the LB service targets a pool, not individual instances.
    pool_name = make_name(run_id, "pool-lb")
    pool_payload = {
        "name": pool_name,
        "description": "tier-4 LB backing pool",
        "size": 1,
        "instance-type": {"id": tiny_id},
        "template": {"id": template_id},
        "disk-size": 10,
    }
    pool = pools.create(pool_payload)
    pool_id = pool.id
    assert pool_id, "pool create returned no id"
    tracker.register("instance-pool", lambda: pools.delete(pool_id), pool_id)
    wait_for_state(lambda: pools.get(pool_id), "running", timeout=600)

    # 2. Load balancer itself (NLB; basic plan).
    lb_name = make_name(run_id, "lb")
    lb = lbs.create({"name": lb_name, "description": "tier-4 smoke"})
    lb_id = lb.id
    assert lb_id, "load-balancer create returned no id"
    tracker.register("load-balancer", lambda: lbs.delete(lb_id), lb_id)
    settled_lb = wait_for_state(lambda: lbs.get(lb_id), "running", timeout=300)
    assert settled_lb.name == lb_name

    # 3. Add a TCP service pointing at the pool. Use a dict payload (matches
    #    the live wire format including the nested healthcheck and instance-pool
    #    reference) — the LoadBalancerService model on this version of the
    #    connector flattens healthcheck fields and lacks instance-pool, so dicts
    #    are the more faithful API exercise.
    svc_name = make_name(run_id, "svc")[:64]
    service_payload = {
        "name": svc_name,
        "description": "tier-4 LB service",
        "protocol": "tcp",
        "port": 80,
        "target-port": 80,
        "strategy": "round-robin",
        "instance-pool": {"id": pool_id},
        "healthcheck": {
            "mode": "tcp",
            "port": 80,
            "interval": 10,
            "timeout": 5,
            "retries": 2,
        },
    }
    lbs.add_service(lb_id, service_payload)
    after_add = lbs.get(lb_id)
    matching = [s for s in (after_add.services or []) if s.name == svc_name]
    assert len(matching) == 1, f"expected service {svc_name!r} on LB"
    svc_id = matching[0].id
    assert svc_id

    # 4. Update the service (change healthcheck interval). The service-update
    #    PUT is a full-resource replace, so resend every required field — only
    #    the healthcheck interval changes between this payload and the create one.
    lbs.update_service(
        lb_id,
        svc_id,
        {
            "name": svc_name,
            "description": "tier-4 LB service (updated)",
            "protocol": "tcp",
            "port": 80,
            "target-port": 80,
            "strategy": "round-robin",
            "instance-pool": {"id": pool_id},
            "healthcheck": {
                "mode": "tcp",
                "port": 80,
                "interval": 20,
                "timeout": 5,
                "retries": 2,
            },
        },
    )

    # 5. Tear down service → LB → pool. Order matters: API forbids deleting a
    #    pool that still has an LB pointing at it.
    lbs.delete_service(lb_id, svc_id)

    assert_safe_name(lb_name)
    lbs.delete(lb_id)
    tracker.unregister(lb_id)

    pools.delete(pool_id)
    tracker.unregister(pool_id)


# ---------------------------------------------------------------------------- #
# DBaaS
# ---------------------------------------------------------------------------- #


def test_dbaas_pg_lifecycle(tier_3_client, run_id, tracker, tier_4_dbaas_enabled) -> None:
    """DBaaS PostgreSQL: create cheapest plan → get → connection info → reveal pw → delete.

    Provisioning a DBaaS service takes 5–15 min. The test asserts secrets are
    present in the responses but never prints them.
    """
    dbaas = DBaaSServiceClient(tier_3_client)
    plan = resolve_cheapest_dbaas_plan(tier_3_client, "pg")
    name = make_name(run_id, "pg")[:50]  # DBaaS service names have a tight length cap

    # Register cleanup BEFORE the create call so a mid-create failure (e.g. the
    # POST succeeds but the re-fetch fails) still leaves a tracked resource
    # for the teardown sweep — DBaaS services are expensive enough that any
    # leak would matter.
    tracker.register("dbaas", lambda: dbaas.delete(name), name)
    # Create with an ip-filter allow-list so the typed field is exercised end to
    # end. (This is a control-plane setting; it does not affect the API calls
    # this test makes.)
    dbaas.create(
        {"plan": plan, "ip-filter": ["203.0.113.0/24"]},
        service_type="pg",
        name=name,
    )

    # State path: rebuilding → running.
    wait_for_state(lambda: dbaas.get(name), "running", timeout=1800, interval=15)
    fetched = dbaas.get(name)
    assert fetched.name == name
    assert (fetched.type or "").lower() == "pg"

    # ip-filter set at create round-trips onto the typed field; update replaces
    # the whole list (it does not merge).
    assert fetched.ip_filter == ["203.0.113.0/24"], (
        f"ip_filter not set on create (got {fetched.ip_filter})"
    )
    dbaas.update(
        name,
        {"ip-filter": ["203.0.113.0/24", "198.51.100.7/32"]},
        service_type="pg",
    )
    wait_for_state(lambda: dbaas.get(name), "running", timeout=600, interval=10)
    assert set(dbaas.get(name).ip_filter or []) == {"203.0.113.0/24", "198.51.100.7/32"}

    # Connection info — get_connection_info returns the full DBaaSService model
    # populated from the type-specific endpoint. Assert structure without ever
    # printing the values.
    conn = dbaas.get_connection_info(name, service_type="pg")
    assert conn.uri_params is not None, "uri-params missing from connection info"
    assert conn.uri_params.host, "connection-info.uri-params.host missing"
    assert conn.uri_params.port, "connection-info.uri-params.port missing"
    assert conn.connection_info is not None, "connection-info block missing"
    # On Postgres the URI field is a list (primary + replicas); assert at least one.
    assert conn.connection_info.uri, "connection-info.uri was empty"

    # Reveal admin password — assert non-empty without ever printing.
    pw = dbaas.reveal_user_password(name, "avnadmin", service_type="pg")
    assert isinstance(pw, dict)
    assert pw.get("password"), "reveal-user-password returned no password"

    # User management (new surface, first live exercise): create a user,
    # confirm it can be deleted again. The username carries the test prefix
    # convention even though users live inside the (already-prefixed) service.
    dbaas.create_user(name, "conn-test-user", service_type="pg")
    wait_for_state(lambda: dbaas.get(name), "running", timeout=600, interval=10)
    dbaas.delete_user(name, "conn-test-user", service_type="pg")

    # update(): set a maintenance window and confirm the service stays healthy.
    dbaas.update(
        name,
        {"maintenance": {"dow": "sunday", "time": "04:00:00"}},
        service_type="pg",
    )
    wait_for_state(lambda: dbaas.get(name), "running", timeout=600, interval=10)

    assert_safe_name(name)
    dbaas.delete(name)
    tracker.unregister(name)


# ---------------------------------------------------------------------------- #
# SKS
# ---------------------------------------------------------------------------- #


def test_sks_lifecycle(tier_3_client, run_id, tracker, tier_4_sks_enabled) -> None:
    """SKS: create cluster → kubeconfig → create nodepool → scale → delete.

    Uses the cheapest service level (``starter`` — free control plane) and a
    single ``standard.small`` worker (block-storage-eligible). Kubeconfig is
    generated but never printed.
    """
    sks = SksClusterClient(tier_3_client)
    small_id = resolve_instance_type(tier_3_client, "standard.small")
    version = resolve_sks_version(tier_3_client)

    # 1. Cluster.
    name = make_name(run_id, "sks")[:50]
    cluster_payload = {
        "name": name,
        "description": "tier-4 SKS smoke",
        "version": version,
        "cni": "calico",
        # API field is "level" (not "service-level"); allowed values are
        # "starter" (free control plane) and "pro".
        "level": "starter",
    }
    cluster = sks.create(cluster_payload)
    cluster_id = cluster.id
    assert cluster_id
    tracker.register("sks-cluster", lambda: sks.delete(cluster_id), cluster_id)
    wait_for_state(lambda: sks.get(cluster_id), "running", timeout=1200, interval=15)

    # 2. Kubeconfig — assert content present; never print. The API requires
    #    both ``user`` and ``groups``; we ask for cluster-admin (system:masters).
    kubeconfig = sks.generate_kubeconfig(
        cluster_id,
        {
            "user": make_name(run_id, "kube")[:32],
            "groups": ["system:masters"],
        },
    )
    assert kubeconfig, "kubeconfig response was empty"
    # The kubeconfig is typically base64-wrapped in {"kubeconfig": "..."};
    # confirm a non-empty value without ever printing the contents.
    values = list(kubeconfig.values()) if isinstance(kubeconfig, dict) else []
    assert any(values), "kubeconfig response carried no value"

    # 3. Nodepool.
    nodepool_name = make_name(run_id, "np")[:32]
    np_payload = SksNodepool(
        name=nodepool_name,
        size=1,
        instance_type={"id": small_id},  # type: ignore[arg-type]
        disk_size=20,
    )
    np_op = sks.create_nodepool(cluster_id, np_payload)
    np_id = np_op.reference_id
    assert np_id, "create_nodepool returned no reference id"
    tracker.register(
        "sks-nodepool",
        lambda: sks.delete_nodepool(cluster_id, np_id),
        np_id,
    )

    # Wait for nodepool to reach running by polling the cluster's embedded list.
    deadline = time.time() + 1200
    while time.time() < deadline:
        cluster_now = sks.get(cluster_id)
        np_now = next((n for n in (cluster_now.nodepools or []) if n.id == np_id), None)
        if np_now and (np_now.state or "").lower() == "running":
            break
        time.sleep(15)
    else:
        raise AssertionError("nodepool never reached running state")

    # 4. Scale: 1 → 2 → 1.
    sks.update_nodepool(cluster_id, np_id, {"size": 2})
    deadline = time.time() + 900
    while time.time() < deadline:
        cluster_now = sks.get(cluster_id)
        np_now = next((n for n in (cluster_now.nodepools or []) if n.id == np_id), None)
        if np_now and np_now.size == 2 and (np_now.state or "").lower() == "running":
            break
        time.sleep(15)
    sks.update_nodepool(cluster_id, np_id, {"size": 1})

    # 5. Tear down nodepool then cluster.
    sks.delete_nodepool(cluster_id, np_id)
    tracker.unregister(np_id)

    assert_safe_name(name)
    sks.delete(cluster_id)
    tracker.unregister(cluster_id)
