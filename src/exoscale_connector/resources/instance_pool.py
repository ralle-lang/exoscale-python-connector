"""Instance Pool resource client.

API reference: https://openapi-v2.exoscale.com/group/endpoint-compute
"""
from __future__ import annotations

from typing import List, Optional

from pydantic import Field

from ..models import ExoscaleModel, Operation, Reference, to_api_payload
from ._base import ResourceClient


class InstancePool(ExoscaleModel):
    """An Exoscale instance pool (autoscaling group of identical instances)."""

    id: Optional[str] = None
    name: Optional[str] = None
    description: Optional[str] = None
    state: Optional[str] = None  # "running" | "scaling-up" | "scaling-down" | ...
    size: Optional[int] = None
    instance_type: Optional[Reference] = None
    template: Optional[Reference] = None
    disk_size: Optional[int] = None
    instance_prefix: Optional[str] = None
    ipv6_enabled: Optional[bool] = None
    public_ip_assignment: Optional[str] = None
    security_groups: List[Reference] = Field(default_factory=list)
    private_networks: List[Reference] = Field(default_factory=list)
    labels: Optional[dict] = None
    instances: List[Reference] = Field(default_factory=list)
    anti_affinity_groups: List[Reference] = Field(default_factory=list)
    deploy_target: Optional[Reference] = None
    ssh_key: Optional[Reference] = None
    created_at: Optional[str] = None


class InstancePoolClient(ResourceClient[InstancePool]):
    """Manage instance pools."""

    collection_path = "instance-pool"
    model = InstancePool
    list_key = "instance-pools"

    def scale(
        self,
        pool_id: str,
        size: int,
        *,
        zone: Optional[str] = None,
        wait: Optional[bool] = None,
    ) -> Operation:
        """Resize an instance pool to the given number of instances.

        The API uses colon-action syntax: ``PUT instance-pool/{id}:scale`` with
        a ``{"size": <n>}`` body.  Returns the async operation, awaited by default.
        """
        zone = self._zone(zone)
        response = self.client.put(
            f"{self.collection_path}/{pool_id}:scale",
            zone=zone,
            json=to_api_payload({"size": size}),
        )
        operation = Operation.model_validate(response)
        if self._should_wait(wait) and operation.id:
            operation = self.client.wait_operation(operation, zone=zone)
        return operation
