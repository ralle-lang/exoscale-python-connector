"""SKS (Scalable Kubernetes Service) resource client.

Covers two related resources:
- :class:`SksCluster` — a managed Kubernetes control plane
- :class:`SksNodepool` — a pool of worker nodes belonging to a cluster

Nodepools are sub-resources of a cluster and are managed through dedicated
methods on :class:`SksClusterClient` rather than through a separate client.

API reference: https://openapi-v2.exoscale.com/
Verified endpoints come from the Ansible playbooks and Python tools in this repo
(see ansible/playbooks/provider/exoscale/sks/ and tools/exoscale/).
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import Field

from ..models import ExoscaleModel, Operation, Reference, to_api_payload
from ._base import ResourceClient


class SksNodepool(ExoscaleModel):
    """A pool of worker nodes within an SKS cluster.

    The API returns nodepools both embedded inside the cluster object and as
    standalone responses when fetching a single nodepool by id.
    """

    id: Optional[str] = None
    name: Optional[str] = None
    description: Optional[str] = None
    size: Optional[int] = None
    state: Optional[str] = None
    # Reference objects for typed sub-resources
    instance_type: Optional[Reference] = None
    template: Optional[Reference] = None
    instance_pool: Optional[Reference] = None
    disk_size: Optional[int] = None
    # Collections of reference objects
    security_groups: Optional[List[Reference]] = None
    anti_affinity_groups: Optional[List[Reference]] = None
    private_networks: Optional[List[Reference]] = None
    labels: Optional[Dict[str, str]] = None
    taints: Optional[Dict[str, str]] = None
    instance_prefix: Optional[str] = None
    public_ip_assignment: Optional[str] = None
    # Nvidia MIG (Multi-Instance GPU) profiles to enable on GPU nodes, keyed by
    # GPU model (e.g. {"a30.24gb": {...}}). Settable on nodepool create/update;
    # returned on the nodepool object. Payload passes through create_nodepool /
    # update_nodepool, which accept a dict or model.
    nvidia_mig_profiles: Optional[Dict[str, Any]] = None


class SksCluster(ExoscaleModel):
    """An Exoscale SKS (managed Kubernetes) cluster."""

    id: Optional[str] = None
    name: Optional[str] = None
    description: Optional[str] = None
    state: Optional[str] = None
    version: Optional[str] = None
    # The TLS endpoint used to reach the Kubernetes API server
    endpoint: Optional[str] = None
    cni: Optional[str] = None
    # "starter" | "pro"
    service_level: Optional[str] = None
    addons: Optional[List[str]] = None
    nodepools: List[SksNodepool] = Field(default_factory=list)
    labels: Optional[Dict[str, str]] = None
    auto_upgrade: Optional[bool] = None
    created_at: Optional[str] = None


class SksClusterClient(ResourceClient[SksCluster]):
    """Manage SKS clusters and their nodepools.

    Cluster CRUD uses the standard :class:`~._base.ResourceClient` verbs.
    Nodepool management is provided as explicit methods because nodepools are
    sub-resources with their own async operations — the same pattern as
    :class:`~.security_group.SecurityGroupClient` rules.
    """

    collection_path = "sks-cluster"
    model = SksCluster
    # Verified from tools/exoscale/exoscale_sks_lab.py:_list_sks_clusters
    list_key = "sks-clusters"

    # ------------------------------------------------------------------ #
    # Cluster helpers
    # ------------------------------------------------------------------ #

    def list_versions(self, *, zone: Optional[str] = None) -> List[str]:
        """Return the Kubernetes versions a new SKS cluster may be created with.

        Wraps ``GET /sks-cluster-version`` (response key
        ``sks-cluster-versions``). The set changes over time as Exoscale adds new
        Kubernetes releases and retires old ones, so resolve a cluster's
        ``version`` against this list rather than hardcoding a literal like
        ``"1.30"`` — a value that is valid today can be rejected after an
        upstream retirement. Mirrors
        :meth:`~.dbaas.DBaaSServiceClient.list_service_types`.

        Versions are returned as raw strings, newest-first as the API orders
        them (e.g. ``["1.31.0", "1.30.4", ...]``).
        """
        payload = self.client.get("sks-cluster-version", zone=self._zone(zone))
        versions = payload.get("sks-cluster-versions") or []
        return [v for v in versions if isinstance(v, str)]

    def generate_kubeconfig(
        self,
        cluster_id: str,
        payload: object,
        *,
        zone: Optional[str] = None,
    ) -> dict:
        """Request a new kubeconfig for a cluster.

        ``payload`` must contain ``user`` (the Kubernetes username to embed in
        the credentials) and ``groups`` (a list of Kubernetes groups, e.g.
        ``["system:masters"]`` for cluster-admin). ``ttl`` is optional.
        The API returns a kubeconfig body (typically base64-encoded).

        Endpoint verified from tools/exoscale/exoscale_sks_lab.py:
        ``POST /sks-cluster-kubeconfig/{cluster_id}``
        """
        zone = self._zone(zone)
        # Kubeconfig lives under a separate top-level path, not under sks-cluster/{id}
        return self.client.post(
            f"sks-cluster-kubeconfig/{cluster_id}",
            zone=zone,
            json=to_api_payload(payload),
        )

    # ------------------------------------------------------------------ #
    # Nodepool sub-resource
    # ------------------------------------------------------------------ #

    def list_nodepools(
        self,
        cluster_id: str,
        *,
        zone: Optional[str] = None,
    ) -> List[SksNodepool]:
        """Return all nodepools belonging to a cluster.

        Nodepools are embedded in the cluster object returned by GET; this
        method fetches the cluster and returns its nodepool list, which avoids
        an extra round-trip and stays consistent with what the Ansible playbooks
        observe (list_keys for nodepool collection is empty — no standalone list
        endpoint was confirmed).
        """
        cluster = self.get(cluster_id, zone=zone)
        return list(cluster.nodepools)

    def get_nodepool(
        self,
        cluster_id: str,
        nodepool_id: str,
        *,
        zone: Optional[str] = None,
    ) -> SksNodepool:
        """Fetch a single nodepool by id.

        Endpoint: ``GET sks-cluster/{cluster_id}/nodepool/{nodepool_id}``
        Verified from tools/exoscale/exoscale_sks_lab.py:_get_sks_nodepool
        """
        zone = self._zone(zone)
        payload = self.client.get(
            f"{self.collection_path}/{cluster_id}/nodepool/{nodepool_id}",
            zone=zone,
        )
        return SksNodepool.model_validate(payload)

    def create_nodepool(
        self,
        cluster_id: str,
        payload: object,
        *,
        zone: Optional[str] = None,
        wait: Optional[bool] = None,
    ) -> Operation:
        """Add a nodepool to an existing cluster.

        Returns the async :class:`~..models.Operation`; the nodepool id is
        carried in ``operation.reference_id`` once it settles.

        Endpoint: ``POST sks-cluster/{cluster_id}/nodepool``
        Verified from tools/exoscale/exoscale_sks_lab.py (line ~737) and
        provision_nodepool.yml.
        """
        zone = self._zone(zone)
        response = self.client.post(
            f"{self.collection_path}/{cluster_id}/nodepool",
            zone=zone,
            json=to_api_payload(payload),
        )
        return self._wait_nodepool_operation(response, zone=zone, wait=wait)

    def update_nodepool(
        self,
        cluster_id: str,
        nodepool_id: str,
        payload: object,
        *,
        zone: Optional[str] = None,
        wait: Optional[bool] = None,
    ) -> Operation:
        """Update a nodepool (PUT).

        Endpoint: ``PUT sks-cluster/{cluster_id}/nodepool/{nodepool_id}``
        Verified from provision_nodepool.yml (update_method PUT,
        update_endpoint_template).
        """
        zone = self._zone(zone)
        response = self.client.put(
            f"{self.collection_path}/{cluster_id}/nodepool/{nodepool_id}",
            zone=zone,
            json=to_api_payload(payload),
        )
        return self._wait_nodepool_operation(response, zone=zone, wait=wait)

    def delete_nodepool(
        self,
        cluster_id: str,
        nodepool_id: str,
        *,
        zone: Optional[str] = None,
        wait: Optional[bool] = None,
    ) -> Operation:
        """Delete a nodepool from a cluster.

        Endpoint: ``DELETE sks-cluster/{cluster_id}/nodepool/{nodepool_id}``
        Verified from tools/exoscale/exoscale_sks_nodepool_ops.py:cmd_delete_nodepool
        """
        zone = self._zone(zone)
        response = self.client.delete(
            f"{self.collection_path}/{cluster_id}/nodepool/{nodepool_id}",
            zone=zone,
        )
        return self._wait_nodepool_operation(response, zone=zone, wait=wait)

    # ------------------------------------------------------------------ #
    # Internal helpers
    # ------------------------------------------------------------------ #

    def _wait_nodepool_operation(
        self,
        response: dict,
        *,
        zone: Optional[str],
        wait: Optional[bool],
    ) -> Operation:
        """Parse a nodepool mutation response and await completion by default."""
        operation = Operation.model_validate(response)
        if self._should_wait(wait) and operation.id:
            operation = self.client.wait_operation(operation, zone=zone)
        return operation
