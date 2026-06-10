# elastic-ip

A reserved public IP address that can be attached to instances or
load-balancers and re-assigned without reconfiguring DNS. Charged while
allocated.

## Model

```python
class ElasticIPHealthcheck(ExoscaleModel):
    mode: Optional[str]
    port: Optional[int]
    uri: Optional[str]
    interval: Optional[int]
    timeout: Optional[int]
    strikes_ok: Optional[int]
    strikes_fail: Optional[int]
    tls_sni: Optional[str]
    tls_skip_verify: Optional[bool]


class ElasticIP(ExoscaleModel):
    id: Optional[str]
    ip: Optional[str]
    description: Optional[str]
    addressfamily: Optional[str]                # "inet4" | "inet6"
    healthcheck: Optional[ElasticIPHealthcheck]
    labels: Optional[Dict[str, str]]
```

## CLI

```bash
exoscale-elastic-ip list
exoscale-elastic-ip get --id <uuid>
exoscale-elastic-ip find --name <description-as-name>
exoscale-elastic-ip create --json '{"description": "web-frontend", "addressfamily": "inet4"}'
exoscale-elastic-ip delete --id <uuid>
```

## Library

```python
from exoscale_connector import ExoscaleClient
from exoscale_connector.resources.elastic_ip import ElasticIPClient

eips = ElasticIPClient(ExoscaleClient.from_env(zone="de-fra-1"))

eip = eips.create({"description": "web-frontend", "addressfamily": "inet4"})
print(eip.ip)        # the assigned public IPv4

eips.update(eip.id, {"description": "web-frontend (production)"})
eips.delete(eip.id)
```

## Gotchas

- **EIPs have no `name` field** — the human label is `description`. The
  client uses `description` as the `name_field` so `find_by_name` works on
  it. Two EIPs with the same description will resolve to the first match.
- **Charged while allocated**, free when attached to a running resource on
  some account types. Delete promptly when no longer needed.
- **Healthcheck is optional** — the EIP itself works as a static address
  without one; configure it when you want EIP-managed failover.
- **Attach to an instance** is done via the instance's update endpoint
  (not exposed on this client).

## End-to-end example

Distilled from
[`tests/integration/test_tier_2.py::test_elastic_ip_lifecycle`](../../tests/integration/test_tier_2.py):

```python
from exoscale_connector import ExoscaleClient
from exoscale_connector.resources.elastic_ip import ElasticIPClient

eips = ElasticIPClient(ExoscaleClient.from_env(zone="de-fra-1"))

eip = eips.create({"description": "smoke-test", "addressfamily": "inet4"})
assert eips.get(eip.id).ip, "the API did not assign an IP"

eips.update(eip.id, {"description": "smoke-test (updated)"})
assert eips.get(eip.id).description == "smoke-test (updated)"

eips.delete(eip.id)
```

## New surfaces (pending live verification)

Reverse DNS (PTR) management, live-tested in Tier 2
(`test_elastic_ip_reverse_dns`) on the next run:

```python
eips.set_reverse_dns(eip.id, "mail.example.com.")
eips.get_reverse_dns(eip.id)                 # "mail.example.com." | None
eips.delete_reverse_dns(eip.id)
```
