"""Compute Instance resource client.

API reference: https://openapi-v2.exoscale.com/group/endpoint-compute
"""

from __future__ import annotations

from pydantic import Field

from ..models import ExoscaleModel, Operation, Reference
from ._base import ResourceClient
from ._reverse_dns import ReverseDNSMixin


class SshKeyReference(ExoscaleModel):
    """Lightweight SSH key reference (name-keyed, not id-keyed)."""

    name: str | None = None


class Instance(ExoscaleModel):
    """An Exoscale compute instance."""

    id: str | None = None
    name: str | None = None
    state: str | None = None  # "running" | "stopped" | "starting" | "stopping" | ...
    instance_type: Reference | None = None
    template: Reference | None = None
    # disk-size is reported in GiB by the API
    disk_size: int | None = None
    # Public IPv4 address (present when the instance has inet4 assignment)
    public_ip: str | None = None
    ipv6_address: str | None = None
    ssh_key: SshKeyReference | None = None
    security_groups: list[Reference] = Field(default_factory=list)
    labels: dict | None = None
    # manager carries pool/cluster membership ({"type": "...", "id": "..."})
    manager: Reference | None = None
    # Placement target the instance is pinned to. Set at create time by passing
    # {"deploy-target": {"id": ...}} in the create payload; discover valid ids
    # with DeployTargetClient. Round-tripped on the response.
    deploy_target: Reference | None = None
    created_at: str | None = None


class InstanceClient(ReverseDNSMixin, ResourceClient[Instance]):
    """Manage compute instances.

    Besides CRUD this client covers lifecycle actions (start/stop/reboot),
    vertical scaling, and the instance's reverse-DNS PTR record
    (via :class:`~exoscale_connector.resources._reverse_dns.ReverseDNSMixin`).
    """

    collection_path = "instance"
    model = Instance
    list_key = "instances"
    _rdns_kind = "instance"

    # ------------------------------------------------------------------ #
    # Lifecycle helpers
    # ------------------------------------------------------------------ #

    def start(
        self,
        instance_id: str,
        *,
        zone: str | None = None,
        wait: bool | None = None,
    ) -> Operation:
        """Start a stopped instance.

        The API uses colon-action syntax with HTTP PUT: ``PUT instance/{id}:start``.
        Returns the async operation, awaited by default.
        """
        zone = self._zone(zone)
        response = self.client.put(f"{self.collection_path}/{instance_id}:start", zone=zone)
        return self._wait_lifecycle_operation(response, zone=zone, wait=wait)

    def stop(
        self,
        instance_id: str,
        *,
        zone: str | None = None,
        wait: bool | None = None,
    ) -> Operation:
        """Stop a running instance gracefully (``PUT instance/{id}:stop``)."""
        zone = self._zone(zone)
        response = self.client.put(f"{self.collection_path}/{instance_id}:stop", zone=zone)
        return self._wait_lifecycle_operation(response, zone=zone, wait=wait)

    def reboot(
        self,
        instance_id: str,
        *,
        zone: str | None = None,
        wait: bool | None = None,
    ) -> Operation:
        """Reboot a running instance (``PUT instance/{id}:reboot``)."""
        zone = self._zone(zone)
        response = self.client.put(f"{self.collection_path}/{instance_id}:reboot", zone=zone)
        return self._wait_lifecycle_operation(response, zone=zone, wait=wait)

    def scale(
        self,
        instance_id: str,
        instance_type_id: str,
        *,
        zone: str | None = None,
        wait: bool | None = None,
    ) -> Operation:
        """Change the instance's compute offering (``PUT instance/{id}:scale``).

        The instance must be **stopped** before scaling. ``instance_type_id``
        is the target offering's UUID (resolve a ``family.size`` slug with
        :meth:`~exoscale_connector.resources.instance_type.InstanceTypeClient.find`).

        Live-verified 2026-06-10 (tier-3 ``test_instance_scale``:
        ``standard.tiny`` → ``standard.small`` on a stopped instance).
        """
        zone = self._zone(zone)
        response = self.client.put(
            f"{self.collection_path}/{instance_id}:scale",
            zone=zone,
            json={"instance-type": {"id": instance_type_id}},
        )
        return self._wait_lifecycle_operation(response, zone=zone, wait=wait)

    # ------------------------------------------------------------------ #
    # Internals
    # ------------------------------------------------------------------ #

    def _wait_lifecycle_operation(
        self,
        response: dict,
        *,
        zone: str | None,
        wait: bool | None,
    ) -> Operation:
        """Parse a lifecycle-action response and await completion unless suppressed."""
        operation = Operation.model_validate(response)
        if self._should_wait(wait) and operation.id:
            operation = self.client.wait_operation(operation, zone=zone)
        return operation
