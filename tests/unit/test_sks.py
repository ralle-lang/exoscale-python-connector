"""Unit tests for SksClusterClient.

All HTTP is intercepted by ``responses``; no network calls are made.
Covers: cluster list/get/create(operation)/delete + nodepool create(operation)/delete
and kebab-case payload serialisation.
"""

from __future__ import annotations

import responses

from exoscale_connector.resources.sks import SksClusterClient, SksNodepool  # noqa: E402

# ------------------------------------------------------------------ #
# Cluster tests
# ------------------------------------------------------------------ #


@responses.activate
def test_list_clusters_returns_typed_models(client, base_url) -> None:
    responses.add(
        responses.GET,
        f"{base_url}/sks-cluster",
        json={
            "sks-clusters": [
                {"id": "cl1", "name": "prod", "state": "running"},
                {"id": "cl2", "name": "staging", "state": "running"},
            ]
        },
        status=200,
    )
    clusters = SksClusterClient(client).list()
    assert [c.name for c in clusters] == ["prod", "staging"]
    assert clusters[0].id == "cl1"


@responses.activate
def test_list_versions_returns_string_list(client, base_url) -> None:
    responses.add(
        responses.GET,
        f"{base_url}/sks-cluster-version",
        json={"sks-cluster-versions": ["1.31.0", "1.30.4", "1.29.8"]},
        status=200,
    )
    versions = SksClusterClient(client).list_versions()
    assert versions == ["1.31.0", "1.30.4", "1.29.8"]


@responses.activate
def test_list_versions_handles_missing_key(client, base_url) -> None:
    responses.add(
        responses.GET,
        f"{base_url}/sks-cluster-version",
        json={},
        status=200,
    )
    assert SksClusterClient(client).list_versions() == []


@responses.activate
def test_get_cluster_returns_typed_model(client, base_url) -> None:
    responses.add(
        responses.GET,
        f"{base_url}/sks-cluster/cl1",
        json={"id": "cl1", "name": "prod", "state": "running", "version": "1.29.0"},
        status=200,
    )
    cluster = SksClusterClient(client).get("cl1")
    assert cluster.id == "cl1"
    assert cluster.version == "1.29.0"


@responses.activate
def test_create_cluster_awaits_operation_and_refetches(client, base_url) -> None:
    # POST returns an async operation referencing the new cluster
    responses.add(
        responses.POST,
        f"{base_url}/sks-cluster",
        json={"id": "op1", "state": "success", "reference": {"id": "cl-new"}},
        status=200,
    )
    # After the operation settles the client re-fetches the resource
    responses.add(
        responses.GET,
        f"{base_url}/sks-cluster/cl-new",
        json={"id": "cl-new", "name": "test-cluster", "state": "running"},
        status=200,
    )
    created = SksClusterClient(client).create({"name": "test-cluster", "cni": "calico"})
    assert created.id == "cl-new"
    assert created.name == "test-cluster"


@responses.activate
def test_delete_cluster_returns_settled_operation(client, base_url) -> None:
    responses.add(
        responses.DELETE,
        f"{base_url}/sks-cluster/cl1",
        json={"id": "op9", "state": "pending"},
        status=200,
    )
    responses.add(
        responses.GET,
        f"{base_url}/operation/op9",
        json={"id": "op9", "state": "success"},
        status=200,
    )
    op = SksClusterClient(client).delete("cl1")
    assert op.state == "success"


# ------------------------------------------------------------------ #
# Nodepool tests
# ------------------------------------------------------------------ #


@responses.activate
def test_list_nodepools_returns_typed_models(client, base_url) -> None:
    # list_nodepools fetches the parent cluster and extracts embedded nodepools
    responses.add(
        responses.GET,
        f"{base_url}/sks-cluster/cl1",
        json={
            "id": "cl1",
            "name": "prod",
            "nodepools": [
                {"id": "np1", "name": "workers", "size": 3},
                {"id": "np2", "name": "gpu", "size": 1},
            ],
        },
        status=200,
    )
    nodepools = SksClusterClient(client).list_nodepools("cl1")
    assert len(nodepools) == 2
    assert nodepools[0].id == "np1"
    assert nodepools[1].name == "gpu"


@responses.activate
def test_create_nodepool_returns_settled_operation(client, base_url) -> None:
    # POST to the nodepool sub-resource path returns an async operation
    responses.add(
        responses.POST,
        f"{base_url}/sks-cluster/cl1/nodepool",
        json={"id": "op2", "state": "pending"},
        status=200,
    )
    responses.add(
        responses.GET,
        f"{base_url}/operation/op2",
        json={"id": "op2", "state": "success", "reference": {"id": "np-new"}},
        status=200,
    )
    op = SksClusterClient(client).create_nodepool(
        "cl1",
        {
            "name": "workers",
            "size": 3,
            "disk-size": 100,
            "instance-type": {"id": "itype-xyz"},
        },
    )
    assert op.state == "success"
    assert op.reference_id == "np-new"


@responses.activate
def test_delete_nodepool_returns_settled_operation(client, base_url) -> None:
    responses.add(
        responses.DELETE,
        f"{base_url}/sks-cluster/cl1/nodepool/np1",
        json={"id": "op3", "state": "pending"},
        status=200,
    )
    responses.add(
        responses.GET,
        f"{base_url}/operation/op3",
        json={"id": "op3", "state": "success"},
        status=200,
    )
    op = SksClusterClient(client).delete_nodepool("cl1", "np1")
    assert op.state == "success"


@responses.activate
def test_create_nodepool_sends_kebab_case_payload(client, base_url) -> None:
    """Verify that snake_case model fields are serialised as kebab-case on the wire."""
    responses.add(
        responses.POST,
        f"{base_url}/sks-cluster/cl1/nodepool",
        json={"id": "op4", "state": "success"},
        status=200,
    )
    # Use a typed model to exercise the alias generator
    nodepool = SksNodepool(
        name="typed-workers",
        size=2,
        disk_size=50,
        instance_type={"id": "itype-abc"},
        public_ip_assignment="inet4",
    )
    SksClusterClient(client).create_nodepool("cl1", nodepool)
    sent = responses.calls[0].request.body
    # snake_case attributes must appear as kebab-case keys in the request
    assert b'"disk-size": 50' in sent
    assert b'"public-ip-assignment": "inet4"' in sent
    assert b'"instance-type"' in sent


@responses.activate
def test_nodepool_nvidia_mig_profiles_round_trips(client, base_url) -> None:
    """nvidia-mig-profiles parses on the nodepool object and serialises kebab-case."""
    responses.add(
        responses.GET,
        f"{base_url}/sks-cluster/cl1/nodepool/np1",
        json={
            "id": "np1",
            "name": "gpu",
            "nvidia-mig-profiles": {"a30.24gb": {"enabled": True}},
        },
        status=200,
    )
    np = SksClusterClient(client).get_nodepool("cl1", "np1")
    assert np.nvidia_mig_profiles == {"a30.24gb": {"enabled": True}}
    # And it serialises back under the kebab-case alias.
    typed = SksNodepool(name="gpu", nvidia_mig_profiles={"a30.24gb": {"enabled": True}})
    assert typed.to_api_payload()["nvidia-mig-profiles"] == {"a30.24gb": {"enabled": True}}
