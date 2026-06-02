"""DNS Domain and Record resource client.

Covers two closely related API groups:

* **DNS Domains** (``/dns-domain``) — zone-level resources; the usual
  collection CRUD is inherited from :class:`ResourceClient`.
* **DNS Records** (``/dns-domain/{id}/record``) — a sub-resource of a domain,
  accessed through dedicated methods on :class:`DnsDomainClient`, mirroring
  the security-group rule pattern.

API reference: https://openapi-v2.exoscale.com/ (tag: dns-domain / dns-record)
Playbook cross-reference:
  ansible/playbooks/provider/exoscale/dns/provision_domain.yml
  ansible/playbooks/provider/exoscale/dns/provision_record.yml
"""
from __future__ import annotations

from typing import Dict, List, Optional

from ..models import ExoscaleModel, Operation, to_api_payload
from ._base import ResourceClient


class DnsDomain(ExoscaleModel):
    """An Exoscale DNS domain (zone)."""

    id: Optional[str] = None
    # The unicode-name field is the human-readable zone name (e.g. "example.com").
    unicode_name: Optional[str] = None
    state: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class DnsRecord(ExoscaleModel):
    """A single DNS record within a domain.

    ``type`` is the record type string: "A", "AAAA", "CNAME", "MX", "TXT", etc.
    ``content`` is the record value (IP address, hostname, text, …).
    ``priority`` is used for MX / SRV records; omit for others.
    """

    id: Optional[str] = None
    name: Optional[str] = None
    type: Optional[str] = None
    content: Optional[str] = None
    ttl: Optional[int] = None
    priority: Optional[int] = None


class DnsDomainClient(ResourceClient[DnsDomain]):
    """Manage DNS domains and their records.

    Domain-level CRUD is provided by the :class:`ResourceClient` base.
    Record management is exposed as sub-resource methods below, matching
    the ``/dns-domain/{id}/record`` and ``/dns-domain/{id}/record/{rid}``
    paths confirmed in the Ansible playbooks.
    """

    collection_path = "dns-domain"
    model = DnsDomain
    list_key = "dns-domains"
    # Domains have no name field in the top-level model; the human label is
    # stored as ``unicode-name``.
    name_field = "unicode_name"

    # ------------------------------------------------------------------ #
    # Record sub-resource
    # ------------------------------------------------------------------ #

    def list_records(
        self, domain_id: str, *, zone: Optional[str] = None
    ) -> List[DnsRecord]:
        """Return all records for a domain.

        The live API responds under the key ``dns-domain-records``. We do
        **not** keep a fallback to the older ``dns-records`` key — a silent
        fallback would mask future API changes; the Tier 1 live test catches
        a wrapper-key change loudly and that is what we want.
        """
        payload = self.client.get(
            f"{self.collection_path}/{domain_id}/record",
            zone=self._zone(zone),
        )
        items = payload.get("dns-domain-records") or []
        return [DnsRecord.model_validate(item) for item in items if isinstance(item, dict)]

    def get_record(
        self,
        domain_id: str,
        record_id: str,
        *,
        zone: Optional[str] = None,
    ) -> DnsRecord:
        """Fetch a single DNS record by its id."""
        payload = self.client.get(
            f"{self.collection_path}/{domain_id}/record/{record_id}",
            zone=self._zone(zone),
        )
        return DnsRecord.model_validate(payload)

    def create_record(
        self,
        domain_id: str,
        record: object,
        *,
        zone: Optional[str] = None,
        wait: Optional[bool] = None,
    ) -> DnsRecord:
        """Create a DNS record and return it once settled.

        ``record`` may be a :class:`DnsRecord` or a plain dict. The API
        responds with an async operation; this method awaits it (unless
        ``wait=False``) then re-fetches the new record by its reference id.
        """
        zone = self._zone(zone)
        response = self.client.post(
            f"{self.collection_path}/{domain_id}/record",
            zone=zone,
            json=to_api_payload(record),
        )
        return self._wait_record_operation(response, domain_id=domain_id, zone=zone, wait=wait)

    def update_record(
        self,
        domain_id: str,
        record_id: str,
        payload: object,
        *,
        zone: Optional[str] = None,
        wait: Optional[bool] = None,
    ) -> DnsRecord:
        """Update a DNS record (HTTP ``PUT``) and return its settled state."""
        zone = self._zone(zone)
        response = self.client.put(
            f"{self.collection_path}/{domain_id}/record/{record_id}",
            zone=zone,
            json=to_api_payload(payload),
        )
        return self._wait_record_operation(
            response, domain_id=domain_id, zone=zone, wait=wait, fallback_id=record_id
        )

    def delete_record(
        self,
        domain_id: str,
        record_id: str,
        *,
        zone: Optional[str] = None,
        wait: Optional[bool] = None,
    ) -> Operation:
        """Delete a DNS record and return the settled operation."""
        zone = self._zone(zone)
        response = self.client.delete(
            f"{self.collection_path}/{domain_id}/record/{record_id}",
            zone=zone,
        )
        return self._wait_operation(response, zone=zone, wait=wait)

    # ------------------------------------------------------------------ #
    # Internals
    # ------------------------------------------------------------------ #

    def _wait_operation(
        self,
        response: Dict,
        *,
        zone: Optional[str],
        wait: Optional[bool],
    ) -> Operation:
        """Await an async operation envelope, mirroring SecurityGroupClient."""
        operation = Operation.model_validate(response)
        if self._should_wait(wait) and operation.id:
            operation = self.client.wait_operation(operation, zone=zone)
        return operation

    def _wait_record_operation(
        self,
        response: Dict,
        *,
        domain_id: str,
        zone: Optional[str],
        wait: Optional[bool],
        fallback_id: Optional[str] = None,
    ) -> DnsRecord:
        """Await an async operation for a record mutation and re-fetch the record.

        If the response is an operation envelope (has ``state`` or ``reference``),
        it is awaited and the record is re-fetched by ``reference.id``. If the
        API returns the record directly, it is validated as-is.
        """
        from ._base import _looks_like_operation  # local import to avoid circular

        if not _looks_like_operation(response):
            return DnsRecord.model_validate(response)

        operation = Operation.model_validate(response)
        if self._should_wait(wait) and operation.id:
            operation = self.client.wait_operation(operation, zone=zone)

        ref_id = operation.reference_id or fallback_id
        if ref_id:
            return self.get_record(domain_id, ref_id, zone=zone)

        # Fallback: surface whatever fields the operation carried.
        return DnsRecord.model_validate(response)
