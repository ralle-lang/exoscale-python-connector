"""Security Group resource client (reference implementation for all asset types).

This module is the canonical example of the per-asset pattern: a pydantic model
describing the resource, an optional nested model, and a :class:`ResourceClient`
subclass that adds only the endpoints unique to this type (here: rule management).
Other asset-type modules mirror this structure.

API reference: https://openapi-v2.exoscale.com/group/endpoint-security-group
"""

from __future__ import annotations

from pydantic import Field

from ..models import ExoscaleModel, Operation, to_api_payload
from ._base import ResourceClient


class SecurityGroupResource(ExoscaleModel):
    """A typed reference to a security group used as a rule source/destination.

    Richer than a bare id-only :class:`~exoscale_connector.models.Reference`
    because an Exoscale-managed **public** security group (e.g. the shared
    ``exoscale-managed-*`` sources) can only be addressed by adding
    ``visibility: "public"`` alongside its ``id``. Private peer groups in your
    own account use ``visibility: "private"`` (the default) or just ``id``.
    Both forms are typed on the request and round-tripped on the response.
    """

    id: str | None = None
    name: str | None = None
    visibility: str | None = None  # "private" | "public"


class SecurityGroupRule(ExoscaleModel):
    """A single ingress/egress rule belonging to a security group."""

    id: str | None = None
    description: str | None = None
    flow_direction: str | None = None  # "ingress" | "egress"
    protocol: str | None = None  # "tcp" | "udp" | "icmp" | ...
    start_port: int | None = None
    end_port: int | None = None
    network: str | None = None  # CIDR, mutually exclusive with security_group
    # Peer/public SG source or destination (mutually exclusive with network).
    security_group: SecurityGroupResource | None = None


class SecurityGroup(ExoscaleModel):
    """An Exoscale security group and its rules."""

    id: str | None = None
    name: str | None = None
    description: str | None = None
    rules: list[SecurityGroupRule] = Field(default_factory=list)
    external_sources: list[str] | None = None


class SecurityGroupClient(ResourceClient[SecurityGroup]):
    """Manage security groups and their rules."""

    collection_path = "security-group"
    model = SecurityGroup
    list_key = "security-groups"

    def add_rule(
        self,
        security_group_id: str,
        rule: object,
        *,
        zone: str | None = None,
        wait: bool | None = None,
    ) -> Operation:
        """Append a rule to a security group.

        ``rule`` may be a :class:`SecurityGroupRule` or a dict. Returns the async
        operation, awaited by default.
        """
        zone = self._zone(zone)
        response = self.client.post(
            f"{self.collection_path}/{security_group_id}/rules",
            zone=zone,
            json=to_api_payload(rule),
        )
        return self._wait_operation(response, zone=zone, wait=wait)

    def delete_rule(
        self,
        security_group_id: str,
        rule_id: str,
        *,
        zone: str | None = None,
        wait: bool | None = None,
    ) -> Operation:
        """Remove a single rule from a security group by rule id."""
        zone = self._zone(zone)
        response = self.client.delete(
            f"{self.collection_path}/{security_group_id}/rules/{rule_id}", zone=zone
        )
        return self._wait_operation(response, zone=zone, wait=wait)

    def _wait_operation(self, response: dict, *, zone: str | None, wait: bool | None) -> Operation:
        """Parse an operation response and await completion unless told not to."""
        operation = Operation.model_validate(response)
        if self._should_wait(wait) and operation.id:
            operation = self.client.wait_operation(operation, zone=zone)
        return operation
