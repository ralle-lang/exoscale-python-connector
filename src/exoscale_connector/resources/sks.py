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

from typing import Any

from pydantic import Field, SerializerFunctionWrapHandler, model_serializer

from ..errors import NotFoundError
from ..models import ExoscaleModel, Operation, Reference, to_api_payload
from ._base import ResourceClient


class SksDeprecatedResource(ExoscaleModel):
    """A Kubernetes API in use on a cluster that a later release removes."""

    group: str | None = None
    version: str | None = None
    resource: str | None = None
    subresource: str | None = None
    # Kubernetes release that removes this API, e.g. "1.32".
    removed_release: str | None = None


class SksOidc(ExoscaleModel):
    """OpenID Connect settings for the cluster's API server."""

    client_id: str | None = None
    issuer_url: str | None = None
    username_claim: str | None = None
    username_prefix: str | None = None
    groups_claim: str | None = None
    groups_prefix: str | None = None
    # Claim-name -> required value pairs a token must carry.
    required_claim: dict[str, str] | None = None


class SksNodepoolTaint(ExoscaleModel):
    """A Kubernetes taint applied to every node in a nodepool."""

    value: str | None = None
    # "NoExecute" | "NoSchedule" | "PreferNoSchedule"
    effect: str | None = None


class SksKubeletImageGc(ExoscaleModel):
    """Kubelet image garbage-collection thresholds for a nodepool."""

    # Disk usage percentages that start / stop image GC.
    high_threshold: int | None = None
    low_threshold: int | None = None
    # Minimum age of an unused image before it may be collected (e.g. "2m").
    min_age: str | None = None


class SksNodepool(ExoscaleModel):
    """A pool of worker nodes within an SKS cluster.

    The API returns nodepools both embedded inside the cluster object and as
    standalone responses when fetching a single nodepool by id.
    """

    id: str | None = None
    name: str | None = None
    description: str | None = None
    size: int | None = None
    state: str | None = None
    # Reference objects for typed sub-resources
    instance_type: Reference | None = None
    template: Reference | None = None
    instance_pool: Reference | None = None
    disk_size: int | None = None
    # Collections of reference objects
    security_groups: list[Reference] | None = None
    anti_affinity_groups: list[Reference] | None = None
    private_networks: list[Reference] | None = None
    labels: dict[str, str] | None = None
    # Keyed by taint key, e.g. {"dedicated": {"value": "gpu", "effect": "NoSchedule"}}
    taints: dict[str, SksNodepoolTaint] | None = None
    instance_prefix: str | None = None
    public_ip_assignment: str | None = None
    # Nvidia MIG (Multi-Instance GPU) profiles to enable on GPU nodes, keyed by
    # GPU model (e.g. {"a30.24gb": {...}}). Settable on nodepool create/update;
    # returned on the nodepool object. Payload passes through create_nodepool /
    # update_nodepool, which accept a dict or model.
    nvidia_mig_profiles: dict[str, Any] | None = None
    # Dedicated-hypervisor / edge placement for the nodepool's instances.
    deploy_target: Reference | None = None
    kubelet_image_gc: SksKubeletImageGc | None = None


class SksCluster(ExoscaleModel):
    """An Exoscale SKS (managed Kubernetes) cluster."""

    id: str | None = None
    name: str | None = None
    description: str | None = None
    state: str | None = None
    version: str | None = None
    # The TLS endpoint used to reach the Kubernetes API server
    endpoint: str | None = None
    cni: str | None = None
    # "starter" | "pro". The wire field is ``level`` (verified live); the
    # attribute keeps its descriptive name and accepts either spelling.
    service_level: str | None = Field(default=None, alias="level")
    addons: list[str] | None = None
    nodepools: list[SksNodepool] = Field(default_factory=list)
    labels: dict[str, str] | None = None
    auto_upgrade: bool | None = None
    oidc: SksOidc | None = None
    # Kubernetes alpha feature gates enabled on the API server.
    feature_gates: list[str] | None = None
    enable_kube_proxy: bool | None = None
    default_security_group_id: str | None = None
    created_at: str | None = None

    @model_serializer(mode="wrap")
    def _omit_empty_nodepools(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        # nodepools is read-only (managed via the nodepool endpoints); never
        # send an empty default list in a create/update body.
        data: dict[str, Any] = handler(self)
        if data.get("nodepools") == []:
            del data["nodepools"]
        return data


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

    def list_versions(self, *, zone: str | None = None) -> list[str]:
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

    def list_deprecated_resources(
        self, cluster_id: str, *, zone: str | None = None
    ) -> list[SksDeprecatedResource]:
        """List deprecated Kubernetes APIs still in use on a cluster.

        Wraps ``GET /sks-cluster-deprecated-resources/{id}``. Run it before a
        version upgrade: anything listed with a ``removed_release`` at or below
        the target version stops being served after the upgrade, so migrate
        those workloads first. An empty list means nothing in use is affected.

        .. warning::
           Implemented from the API reference — pending live verification.
        """
        payload = self.client.get(
            f"sks-cluster-deprecated-resources/{cluster_id}", zone=self._zone(zone)
        )
        # The spec documents a bare array, which the client wraps as "data";
        # accept the keyed shape other SKS listings use as well.
        items = payload.get("data") or payload.get("sks-cluster-deprecated-resources") or []
        return [SksDeprecatedResource.model_validate(i) for i in items if isinstance(i, dict)]

    def generate_kubeconfig(
        self,
        cluster_id: str,
        payload: object,
        *,
        zone: str | None = None,
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

    def upgrade(
        self,
        cluster_id: str,
        version: str,
        *,
        zone: str | None = None,
        wait: bool | None = None,
    ) -> Operation:
        """Upgrade the control plane to ``version`` (``PUT sks-cluster/{id}/upgrade``).

        Pick ``version`` from :meth:`list_versions` and check
        :meth:`list_deprecated_resources` first.
        """
        zone = self._zone(zone)
        response = self.client.put(
            f"{self.collection_path}/{cluster_id}/upgrade",
            zone=zone,
            json={"version": version},
        )
        return self._wait_nodepool_operation(response, zone=zone, wait=wait)

    def upgrade_service_level(
        self,
        cluster_id: str,
        *,
        zone: str | None = None,
        wait: bool | None = None,
    ) -> Operation:
        """Move a ``starter`` cluster to ``pro`` (``PUT .../upgrade-service-level``).

        One-way: there is no downgrade endpoint, and ``pro`` is billed.
        """
        zone = self._zone(zone)
        response = self.client.put(
            f"{self.collection_path}/{cluster_id}/upgrade-service-level",
            zone=zone,
        )
        return self._wait_nodepool_operation(response, zone=zone, wait=wait)

    def rotate_ccm_credentials(
        self,
        cluster_id: str,
        *,
        zone: str | None = None,
        wait: bool | None = None,
    ) -> Operation:
        """Rotate the cloud-controller-manager credentials (``PUT .../rotate-ccm-credentials``)."""
        zone = self._zone(zone)
        response = self.client.put(
            f"{self.collection_path}/{cluster_id}/rotate-ccm-credentials",
            zone=zone,
        )
        return self._wait_nodepool_operation(response, zone=zone, wait=wait)

    def rotate_csi_credentials(
        self,
        cluster_id: str,
        *,
        zone: str | None = None,
        wait: bool | None = None,
    ) -> Operation:
        """Rotate the CSI driver credentials (``PUT .../rotate-csi-credentials``)."""
        zone = self._zone(zone)
        response = self.client.put(
            f"{self.collection_path}/{cluster_id}/rotate-csi-credentials",
            zone=zone,
        )
        return self._wait_nodepool_operation(response, zone=zone, wait=wait)

    def rotate_karpenter_credentials(
        self,
        cluster_id: str,
        *,
        zone: str | None = None,
        wait: bool | None = None,
    ) -> Operation:
        """Rotate the Karpenter credentials (``PUT .../rotate-karpenter-credentials``)."""
        zone = self._zone(zone)
        response = self.client.put(
            f"{self.collection_path}/{cluster_id}/rotate-karpenter-credentials",
            zone=zone,
        )
        return self._wait_nodepool_operation(response, zone=zone, wait=wait)

    def rotate_operators_ca(
        self,
        cluster_id: str,
        *,
        zone: str | None = None,
        wait: bool | None = None,
    ) -> Operation:
        """Rotate the operators certificate authority (``PUT .../rotate-operators-ca``)."""
        zone = self._zone(zone)
        response = self.client.put(
            f"{self.collection_path}/{cluster_id}/rotate-operators-ca",
            zone=zone,
        )
        return self._wait_nodepool_operation(response, zone=zone, wait=wait)

    def get_authority_cert(
        self, cluster_id: str, authority: str, *, zone: str | None = None
    ) -> str | None:
        """Return a cluster CA certificate (``GET .../authority/{authority}/cert``).

        ``authority`` is ``"control-plane"``, ``"aggregation"`` or ``"kubelet"``.
        The value is the ``cacert`` string as the API returns it.
        """
        payload = self.client.get(
            f"{self.collection_path}/{cluster_id}/authority/{authority}/cert",
            zone=self._zone(zone),
        )
        value = payload.get("cacert")
        return value if isinstance(value, str) else None

    def get_inspection(self, cluster_id: str, *, zone: str | None = None) -> dict | None:
        """Return the last cluster diagnostic report (``GET sks-cluster/{id}/inspection``).

        The shape is free-form in the spec, so it is returned as a plain dict.
        Returns ``None`` when no inspection has run yet: the API answers 404
        "Couldn't find last inspection" for a fresh cluster (observed live).
        """
        try:
            return self.client.get(
                f"{self.collection_path}/{cluster_id}/inspection", zone=self._zone(zone)
            )
        except NotFoundError:
            return None

    def generate_karpenter_nodeclass(
        self, cluster_id: str, *, zone: str | None = None
    ) -> str | None:
        """Generate an ``ExoscaleNodeClass`` manifest for Karpenter.

        Endpoint: ``PUT sks-cluster/{id}/generate-karpenter-exoscale-nodeclass``;
        returns the manifest string.
        """
        payload = self.client.put(
            f"{self.collection_path}/{cluster_id}/generate-karpenter-exoscale-nodeclass",
            zone=self._zone(zone),
        )
        value = payload.get("exoscale-nodeclass")
        return value if isinstance(value, str) else None

    def generate_karpenter_nodepool(
        self, cluster_id: str, *, zone: str | None = None
    ) -> str | None:
        """Generate a Karpenter ``NodePool`` manifest.

        Endpoint: ``PUT sks-cluster/{id}/generate-karpenter-nodepool``; returns
        the manifest string.
        """
        payload = self.client.put(
            f"{self.collection_path}/{cluster_id}/generate-karpenter-nodepool",
            zone=self._zone(zone),
        )
        value = payload.get("nodepool")
        return value if isinstance(value, str) else None

    # ------------------------------------------------------------------ #
    # Nodepool sub-resource
    # ------------------------------------------------------------------ #

    def list_nodepools(
        self,
        cluster_id: str,
        *,
        zone: str | None = None,
    ) -> list[SksNodepool]:
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
        zone: str | None = None,
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
        zone: str | None = None,
        wait: bool | None = None,
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
        zone: str | None = None,
        wait: bool | None = None,
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
        zone: str | None = None,
        wait: bool | None = None,
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

    def scale_nodepool(
        self,
        cluster_id: str,
        nodepool_id: str,
        size: int,
        *,
        zone: str | None = None,
        wait: bool | None = None,
    ) -> Operation:
        """Set the size of a nodepool (``PUT .../nodepool/{id}:scale``).

        The dedicated scale action; ``update_nodepool`` with a ``size``
        also works but is a full update.
        """
        zone = self._zone(zone)
        response = self.client.put(
            f"{self.collection_path}/{cluster_id}/nodepool/{nodepool_id}:scale",
            zone=zone,
            json={"size": size},
        )
        return self._wait_nodepool_operation(response, zone=zone, wait=wait)

    def evict_nodepool_members(
        self,
        cluster_id: str,
        nodepool_id: str,
        instance_ids: list[str],
        *,
        zone: str | None = None,
        wait: bool | None = None,
    ) -> Operation:
        """Remove named nodes from a nodepool (``PUT .../nodepool/{id}:evict``).

        ``instance_ids`` are member instances of the nodepool (see its
        ``instance_pool``); they are drained and destroyed, and the size
        shrinks to match.
        """
        zone = self._zone(zone)
        response = self.client.put(
            f"{self.collection_path}/{cluster_id}/nodepool/{nodepool_id}:evict",
            zone=zone,
            json={"instances": list(instance_ids)},
        )
        return self._wait_nodepool_operation(response, zone=zone, wait=wait)

    # ------------------------------------------------------------------ #
    # Internal helpers
    # ------------------------------------------------------------------ #

    def _wait_nodepool_operation(
        self,
        response: dict,
        *,
        zone: str | None,
        wait: bool | None,
    ) -> Operation:
        """Parse a nodepool mutation response and await completion by default."""
        operation = Operation.model_validate(response)
        if self._should_wait(wait) and operation.id:
            operation = self.client.wait_operation(operation, zone=zone)
        return operation
