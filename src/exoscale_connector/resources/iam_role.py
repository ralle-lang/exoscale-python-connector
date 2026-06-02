"""IAM role resource client.

IAM roles are account-global resources defining a named permission set with an
optional inline policy. They are reached through a zone host — supply a zone
when constructing the client or per-call.

Create and update are asynchronous; the base :meth:`create` / :meth:`update`
implementation handles the operation envelope and re-fetches the settled
resource automatically.

API reference: https://openapi-v2.exoscale.com/group/endpoint-iam
"""
from __future__ import annotations

from enum import Enum
from typing import Dict, Iterable, List, Optional, Union

from ..models import ExoscaleModel, Operation, to_api_payload
from ._base import ResourceClient


# These enums name the closed value sets the API accepts. They subclass ``str``,
# so a member is interchangeable with its string value: it serialises identically
# and equality with the raw string holds. The model fields stay typed as ``str``
# (not the enum) so callers may still pass any value the API later introduces —
# the enums are an opt-in convenience for discoverability, never a constraint.
class RuleAction(str, Enum):
    """Allowed values for :attr:`IAMPolicyRule.action`."""

    ALLOW = "allow"
    DENY = "deny"


class ServiceType(str, Enum):
    """Allowed values for :attr:`IAMPolicyService.type`."""

    ALLOW = "allow"
    DENY = "deny"
    RULES = "rules"


class ServiceStrategy(str, Enum):
    """Allowed values for :attr:`IAMPolicy.default_service_strategy`."""

    ALLOW = "allow"
    DENY = "deny"


class IAMPolicyRule(ExoscaleModel):
    """A single rule inside a service's rule list.

    Rules are evaluated in order; the first whose :attr:`expression` matches
    decides the outcome via :attr:`action`. The expression is Exoscale's
    service-specific condition language (a CEL-like DSL such as
    ``resources.bucket != "backups"`` or ``operation in ['list-dns-domains']``)
    and is deliberately kept as a free-form string — the connector never parses
    it. ``extra="allow"`` on the base model preserves any field not modelled here.

    Use :meth:`allow` / :meth:`deny` to build a rule without spelling out
    ``action``.
    """

    # "allow" or "deny".
    action: Optional[str] = None
    # The condition expression in Exoscale's IAM DSL (kept verbatim).
    expression: Optional[str] = None
    # Optional resource scopes; modern policies usually express these inside the
    # expression instead, but the field remains part of the API contract.
    resources: Optional[List[str]] = None

    @classmethod
    def allow(cls, expression: str, *, resources: Optional[List[str]] = None) -> IAMPolicyRule:
        """A rule that *allows* the call when ``expression`` evaluates true."""
        return cls(action=RuleAction.ALLOW.value, expression=expression, resources=resources)

    @classmethod
    def deny(cls, expression: str, *, resources: Optional[List[str]] = None) -> IAMPolicyRule:
        """A rule that *denies* the call when ``expression`` evaluates true."""
        return cls(action=RuleAction.DENY.value, expression=expression, resources=resources)


class IAMPolicyService(ExoscaleModel):
    """The policy block for one service class (e.g. ``compute``, ``sos``).

    :attr:`type` is ``"allow"`` / ``"deny"`` for a blanket decision, or
    ``"rules"`` when :attr:`rules` carries an ordered rule list. Use
    :meth:`allow` / :meth:`deny` / :meth:`with_rules` to build one directly.
    """

    # "allow", "deny", or "rules".
    type: Optional[str] = None
    # Present (and meaningful) when ``type == "rules"``.
    rules: Optional[List[IAMPolicyRule]] = None

    @classmethod
    def allow(cls) -> IAMPolicyService:
        """A blanket *allow* for this service."""
        return cls(type=ServiceType.ALLOW.value)

    @classmethod
    def deny(cls) -> IAMPolicyService:
        """A blanket *deny* for this service."""
        return cls(type=ServiceType.DENY.value)

    @classmethod
    def with_rules(cls, *rules: IAMPolicyRule) -> IAMPolicyService:
        """A rule-based block; rules are evaluated top-to-bottom."""
        return cls(type=ServiceType.RULES.value, rules=list(rules))


class IAMPolicy(ExoscaleModel):
    """The inline policy attached to an IAM role.

    The policy decides access per service class: :attr:`services` maps a service
    name (an open set — new services appear over time) to its
    :class:`IAMPolicyService` block, and :attr:`default_service_strategy` is the
    fallback for any service not listed. ``extra="allow"`` on the base model
    preserves keys the connector does not yet model.

    :meth:`deny_all` / :meth:`allow_all` / :meth:`allow_services` cover the common
    blanket-strategy policies in one call; compose :class:`IAMPolicyService` and
    :class:`IAMPolicyRule` by hand for rule-based policies.
    """

    # Fallback decision for unconfigured services: "allow" or "deny".
    default_service_strategy: Optional[str] = None
    # Per-service policy blocks, keyed by service name.
    services: Optional[Dict[str, IAMPolicyService]] = None

    @classmethod
    def deny_all(cls) -> IAMPolicy:
        """Deny everything: default-deny with no service exceptions."""
        return cls(default_service_strategy=ServiceStrategy.DENY.value, services={})

    @classmethod
    def allow_all(cls) -> IAMPolicy:
        """Allow everything: default-allow with no service exceptions."""
        return cls(default_service_strategy=ServiceStrategy.ALLOW.value, services={})

    @classmethod
    def allow_services(cls, services: Iterable[str]) -> IAMPolicy:
        """Default-deny, then blanket-allow only the named services."""
        return cls(
            default_service_strategy=ServiceStrategy.DENY.value,
            services={name: IAMPolicyService.allow() for name in services},
        )


class IAMRole(ExoscaleModel):
    """An Exoscale IAM role."""

    id: Optional[str] = None
    name: Optional[str] = None
    description: Optional[str] = None
    # Whether the role can be modified after creation (some built-in roles are
    # read-only and the API marks them with editable=false).
    editable: Optional[bool] = None
    permissions: Optional[List[str]] = None
    labels: Optional[Dict[str, str]] = None
    # The role's permission policy (what a key bound to this role may do).
    policy: Optional[IAMPolicy] = None
    # Conditions under which this role may be assumed; same policy shape.
    assume_role_policy: Optional[IAMPolicy] = None


class IAMRoleClient(ResourceClient[IAMRole]):
    """Manage Exoscale IAM roles.

    Inline ``policy`` / ``assume_role_policy`` on :meth:`create` are accepted by
    the API. Changing them on an *existing* role, however, goes through dedicated
    sub-endpoints — the generic :meth:`update` only PUTs the role's own
    attributes (name, description, permissions, labels). Use :meth:`set_policy`
    and :meth:`set_assume_role_policy` for policy changes.
    """

    collection_path = "iam-role"
    model = IAMRole
    list_key = "iam-roles"

    def set_policy(
        self,
        role_id: str,
        policy: Union[IAMPolicy, dict],
        *,
        zone: Optional[str] = None,
        wait: Optional[bool] = None,
    ) -> Operation:
        """Replace the role's permission policy (``PUT /iam-role/{id}:policy``)."""
        return self._put_policy(role_id, "policy", policy, zone=zone, wait=wait)

    def set_assume_role_policy(
        self,
        role_id: str,
        policy: Union[IAMPolicy, dict],
        *,
        zone: Optional[str] = None,
        wait: Optional[bool] = None,
    ) -> Operation:
        """Replace the assume-role policy (``PUT /iam-role/{id}:assume-role-policy``)."""
        return self._put_policy(role_id, "assume-role-policy", policy, zone=zone, wait=wait)

    def _put_policy(
        self,
        role_id: str,
        action: str,
        policy: Union[IAMPolicy, dict],
        *,
        zone: Optional[str],
        wait: Optional[bool],
    ) -> Operation:
        """PUT a policy body to an ``:<action>`` sub-endpoint and await the op."""
        zone = self._zone(zone)
        response = self.client.put(
            f"{self.collection_path}/{role_id}:{action}",
            zone=zone,
            json=to_api_payload(policy),
        )
        operation = Operation.model_validate(response)
        if self._should_wait(wait) and operation.id:
            operation = self.client.wait_operation(operation, zone=zone)
        return operation
