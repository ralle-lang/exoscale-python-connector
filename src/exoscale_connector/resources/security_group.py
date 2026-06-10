"""Security Group resource client (reference implementation for all asset types).

This module is the canonical example of the per-asset pattern: a pydantic model
describing the resource, an optional nested model, and a :class:`ResourceClient`
subclass that adds only the endpoints unique to this type (here: rule management).
Other asset-type modules mirror this structure.

API reference: https://openapi-v2.exoscale.com/group/endpoint-security-group
"""
from __future__ import annotations

from typing import List, Optional

from pydantic import Field

from ..models import ExoscaleModel, Operation, Reference, to_api_payload
from ._base import ResourceClient


class SecurityGroupRule(ExoscaleModel):
    """A single ingress/egress rule belonging to a security group."""

    id: Optional[str] = None
    description: Optional[str] = None
    flow_direction: Optional[str] = None  # "ingress" | "egress"
    protocol: Optional[str] = None  # "tcp" | "udp" | "icmp" | ...
    start_port: Optional[int] = None
    end_port: Optional[int] = None
    network: Optional[str] = None  # CIDR, mutually exclusive with security_group
    security_group: Optional[Reference] = None


class SecurityGroup(ExoscaleModel):
    """An Exoscale security group and its rules."""

    id: Optional[str] = None
    name: Optional[str] = None
    description: Optional[str] = None
    rules: List[SecurityGroupRule] = Field(default_factory=list)
    external_sources: Optional[List[str]] = None


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
        zone: Optional[str] = None,
        wait: Optional[bool] = None,
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
        zone: Optional[str] = None,
        wait: Optional[bool] = None,
    ) -> Operation:
        """Remove a single rule from a security group by rule id."""
        zone = self._zone(zone)
        response = self.client.delete(
            f"{self.collection_path}/{security_group_id}/rules/{rule_id}", zone=zone
        )
        return self._wait_operation(response, zone=zone, wait=wait)

    def _wait_operation(
        self, response: dict, *, zone: Optional[str], wait: Optional[bool]
    ) -> Operation:
        """Parse an operation response and await completion unless told not to."""
        operation = Operation.model_validate(response)
        if self._should_wait(wait) and operation.id:
            operation = self.client.wait_operation(operation, zone=zone)
        return operation
