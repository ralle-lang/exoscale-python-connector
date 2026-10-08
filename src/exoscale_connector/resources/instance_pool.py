"""Instance Pool resource client.

API reference: https://openapi-v2.exoscale.com/group/endpoint-compute
"""

from __future__ import annotations

from pydantic import Field

from ..models import ExoscaleModel, Operation, Reference, to_api_payload
from ._base import ResourceClient
from .instance import SshKeyReference


class InstancePool(ExoscaleModel):
    """An Exoscale instance pool (autoscaling group of identical instances)."""

    id: str | None = None
    name: str | None = None
    description: str | None = None
    state: str | None = None  # "running" | "scaling-up" | "scaling-down" | ...
    size: int | None = None
    instance_type: Reference | None = None
    template: Reference | None = None
    disk_size: int | None = None
    instance_prefix: str | None = None
    ipv6_enabled: bool | None = None
    public_ip_assignment: str | None = None
    security_groups: list[Reference] = Field(default_factory=list)
    private_networks: list[Reference] = Field(default_factory=list)
    labels: dict | None = None
    instances: list[Reference] = Field(default_factory=list)
    anti_affinity_groups: list[Reference] = Field(default_factory=list)
    deploy_target: Reference | None = None
    ssh_key: Reference | None = None
    created_at: str | None = None
    elastic_ips: list[Reference] | None = None
    # Every key on the pool's instances; `ssh_key` is the single-key shorthand.
    ssh_keys: list[SshKeyReference] | None = None
    # Cloud-init user data for new members, base64-encoded.
    user_data: str | None = None
    # Floor of running members kept during rolling operations.
    min_available: int | None = None


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
        zone: str | None = None,
        wait: bool | None = None,
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
