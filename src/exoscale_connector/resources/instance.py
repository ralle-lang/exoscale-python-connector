"""Compute Instance resource client.

API reference: https://openapi-v2.exoscale.com/group/endpoint-compute
"""
from __future__ import annotations

from typing import List, Optional

from ..models import ExoscaleModel, Operation, Reference
from ._base import ResourceClient


class SshKeyReference(ExoscaleModel):
    """Lightweight SSH key reference (name-keyed, not id-keyed)."""

    name: Optional[str] = None


class Instance(ExoscaleModel):
    """An Exoscale compute instance."""

    id: Optional[str] = None
    name: Optional[str] = None
    state: Optional[str] = None  # "running" | "stopped" | "starting" | "stopping" | ...
    instance_type: Optional[Reference] = None
    template: Optional[Reference] = None
    # disk-size is reported in GiB by the API
    disk_size: Optional[int] = None
    # Public IPv4 address (present when the instance has inet4 assignment)
    public_ip: Optional[str] = None
    ipv6_address: Optional[str] = None
    ssh_key: Optional[SshKeyReference] = None
    security_groups: List[Reference] = []
    labels: Optional[dict] = None
    # manager carries pool/cluster membership ({"type": "...", "id": "..."})
    manager: Optional[Reference] = None
    created_at: Optional[str] = None


class InstanceClient(ResourceClient[Instance]):
    """Manage compute instances."""

    collection_path = "instance"
    model = Instance
    list_key = "instances"

    # ------------------------------------------------------------------ #
    # Lifecycle helpers
    # ------------------------------------------------------------------ #

    def start(
        self,
        instance_id: str,
        *,
        zone: Optional[str] = None,
        wait: Optional[bool] = None,
    ) -> Operation:
        """Start a stopped instance.

        The API uses colon-action syntax with HTTP PUT: ``PUT instance/{id}:start``.
        Returns the async operation, awaited by default.
        """
        zone = self._zone(zone)
        response = self.client.put(
            f"{self.collection_path}/{instance_id}:start", zone=zone
        )
        return self._wait_lifecycle_operation(response, zone=zone, wait=wait)

    def stop(
        self,
        instance_id: str,
        *,
        zone: Optional[str] = None,
        wait: Optional[bool] = None,
    ) -> Operation:
        """Stop a running instance gracefully (``PUT instance/{id}:stop``)."""
        zone = self._zone(zone)
        response = self.client.put(
            f"{self.collection_path}/{instance_id}:stop", zone=zone
        )
        return self._wait_lifecycle_operation(response, zone=zone, wait=wait)

    def reboot(
        self,
        instance_id: str,
        *,
        zone: Optional[str] = None,
        wait: Optional[bool] = None,
    ) -> Operation:
        """Reboot a running instance (``PUT instance/{id}:reboot``)."""
        zone = self._zone(zone)
        response = self.client.put(
            f"{self.collection_path}/{instance_id}:reboot", zone=zone
        )
        return self._wait_lifecycle_operation(response, zone=zone, wait=wait)

    # ------------------------------------------------------------------ #
    # Internals
    # ------------------------------------------------------------------ #

    def _wait_lifecycle_operation(
        self,
        response: dict,
        *,
        zone: Optional[str],
        wait: Optional[bool],
    ) -> Operation:
        """Parse a lifecycle-action response and await completion unless suppressed."""
        operation = Operation.model_validate(response)
        if self._should_wait(wait) and operation.id:
            operation = self.client.wait_operation(operation, zone=zone)
        return operation
