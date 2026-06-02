# private-network

An L2/L3 private network attached to a zone. Two flavours: **unmanaged**
(simple shared L2, no IP allocation) or **managed** (DHCP with API-allocated
IPs from `start-ip`/`end-ip`).

## Model

```python
class PrivateNetwork(ExoscaleModel):
    id: Optional[str]
    name: Optional[str]
    description: Optional[str]
    start_ip: Optional[str]   # managed networks only
    end_ip: Optional[str]     # managed networks only
    netmask: Optional[str]    # managed networks only
    labels: Optional[Dict[str, str]]
```

## CLI

```bash
exoscale-private-network list
exoscale-private-network get --id <uuid>
exoscale-private-network find --name <name>
exoscale-private-network create --json '{"name": "internal", "description": "service mesh"}'
exoscale-private-network delete --id <uuid>
```

## Library

```python
from exoscale_connector import ExoscaleClient
from exoscale_connector.resources.private_network import PrivateNetworkClient

pn = PrivateNetworkClient(ExoscaleClient.from_env(zone="de-fra-1"))

# Unmanaged (shared L2)
network = pn.create({"name": "internal", "description": "service mesh"})

# Managed (DHCP)
network = pn.create({
    "name": "managed-internal",
    "start-ip": "10.0.0.10",
    "end-ip":   "10.0.0.250",
    "netmask":  "255.255.255.0",
})

# Update + delete
pn.update(network.id, {"description": "updated"})
pn.delete(network.id)
```

## Gotchas

- **Instance attach/detach is not exposed in the current connector** —
  attaching an instance to a private network is done via the instance's
  own update endpoint (not yet covered here). Tracked as a follow-up.
- **Managed networks need all three of `start-ip`, `end-ip`, `netmask`**;
  unmanaged networks need none.

## End-to-end example

Distilled from
[`tests/integration/test_tier_1.py::test_private_network_lifecycle`](../../tests/integration/test_tier_1.py):

```python
from exoscale_connector import ExoscaleClient
from exoscale_connector.resources.private_network import PrivateNetworkClient

pn = PrivateNetworkClient(ExoscaleClient.from_env(zone="de-fra-1"))

# 1. Create + verify
network = pn.create({"name": "internal", "description": "tier-1 smoke"})
assert pn.get(network.id).name == "internal"

# 2. Update
pn.update(network.id, {"description": "updated"})
assert pn.get(network.id).description == "updated"

# 3. Cleanup
pn.delete(network.id)
```
