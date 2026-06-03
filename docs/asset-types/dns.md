# dns (domain + records)

A DNS zone in your Exoscale account plus the records it contains. The zone
is the parent resource (a *domain*) and records are sub-resources accessed
via `/dns-domain/<id>/record/...`.

## Model

```python
class DnsDomain(ExoscaleModel):
    id: Optional[str]
    unicode_name: Optional[str]   # the zone's human name (e.g. "example.com")
    state: Optional[str]
    created_at: Optional[str]
    updated_at: Optional[str]


class DnsRecord(ExoscaleModel):
    id: Optional[str]
    name: Optional[str]           # subdomain (e.g. "www"); "" or "@" for apex
    type: Optional[str]           # "A" | "AAAA" | "CNAME" | "MX" | "TXT" | ...
    content: Optional[str]        # IP, hostname, text, ...
    ttl: Optional[int]
    priority: Optional[int]       # used for MX / SRV; omit for A/AAAA/...
```

## CLI

The shared harness emits `<verb>-domain` / `<verb>-record` commands because DNS
has both domain- and record-level resources:

```bash
exoscale-dns list-domains
exoscale-dns get-domain --id <uuid>
exoscale-dns create-domain --json '{"unicode-name": "example.test"}'
exoscale-dns delete-domain --id <uuid>

exoscale-dns list-records --domain-id <uuid>
exoscale-dns create-record --domain-id <uuid> --json '{"name": "www", "type": "A", "content": "192.0.2.1", "ttl": 3600}'
exoscale-dns delete-record --domain-id <uuid> --id <uuid>
```

## Library

```python
from exoscale_connector import ExoscaleClient
from exoscale_connector.resources.dns import DnsDomainClient

dns = DnsDomainClient(ExoscaleClient.from_env(zone="de-fra-1"))

# Zones
zone = dns.create({"unicode-name": "example.test"})
domains = dns.list()
dns.delete(zone.id)

# Records (sub-resource methods on DnsDomainClient)
record = dns.create_record(zone.id, {
    "name": "www", "type": "A", "content": "192.0.2.1", "ttl": 3600,
})
records = dns.list_records(zone.id)
dns.update_record(zone.id, record.id, {"ttl": 7200})
dns.delete_record(zone.id, record.id)
```

## Gotchas

- **List wrapper key is `dns-domain-records`, not `dns-records`.** An early
  version used the wrong key and `list_records` always came back empty; live
  testing caught it. The connector now reads `dns-domain-records` only — no
  silent fallback, so a future wrapper-key change fails loudly instead of
  returning an empty list.
- **`.test` TLD is reserved (RFC 2606)** — use it for test zones; they
  won't resolve publicly even when delegated, which is fine for an
  isolated test environment.
- **`unicode-name` is the zone label**, not a generic `name` field. The
  client sets `name_field = "unicode_name"` so `find_by_name` works on it.
- **Account DNS quota.** Most accounts have a cap on the number of DNS
  zones you can have at once. A `400: DNS subscription limit reached`
  means you need to free a slot or raise the limit.

## End-to-end example

Distilled from
[`tests/integration/test_tier_1.py::test_dns_lifecycle`](../../tests/integration/test_tier_1.py):

```python
from exoscale_connector import ExoscaleClient
from exoscale_connector.resources.dns import DnsDomainClient

dns = DnsDomainClient(ExoscaleClient.from_env(zone="de-fra-1"))

# 1. Create zone
zone = dns.create({"unicode-name": "smoke-test.test"})
zone_id = zone.id

# 2. Add a record
rec = dns.create_record(zone_id, {
    "name": "www", "type": "A", "content": "192.0.2.1", "ttl": 3600,
})

# 3. Verify
listed = dns.list_records(zone_id)
assert any(r.id == rec.id for r in listed)

# 4. Update TTL
dns.update_record(zone_id, rec.id, {"ttl": 7200})
assert dns.get_record(zone_id, rec.id).ttl == 7200

# 5. Cleanup (records first, then zone)
dns.delete_record(zone_id, rec.id)
dns.delete(zone_id)
```
