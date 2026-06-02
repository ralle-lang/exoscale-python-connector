# load-balancer (+ services)

A Network Load Balancer (NLB). Services are sub-resources that define
how incoming traffic on a port maps to a backing instance pool.

## Model

```python
class LoadBalancerService(ExoscaleModel):
    id: Optional[str]
    name: Optional[str]
    description: Optional[str]
    protocol: Optional[str]                  # "tcp" | "udp"
    port: Optional[int]                      # public-facing port
    target_port: Optional[int]               # port on the backing instances
    strategy: Optional[str]                  # "round-robin" | "source-hash"
    healthcheck_mode: Optional[str]          # "tcp" | "http" | "https"
    healthcheck_port: Optional[int]
    healthcheck_uri: Optional[str]
    healthcheck_interval: Optional[int]
    healthcheck_timeout: Optional[int]
    healthcheck_retries: Optional[int]
    healthcheck_tls_sni: Optional[str]
    state: Optional[str]


class LoadBalancer(ExoscaleModel):
    id: Optional[str]
    name: Optional[str]
    description: Optional[str]
    ip: Optional[str]                        # public IP allocated to the LB
    state: Optional[str]
    labels: Optional[Dict[str, str]]
    services: Optional[List[LoadBalancerService]]
```

## CLI

```bash
exoscale-load-balancer list
exoscale-load-balancer get --id <uuid>
exoscale-load-balancer find --name <name>
exoscale-load-balancer create --json '{"name": "web-lb", "description": "public web LB"}'
exoscale-load-balancer delete --id <uuid>
```

> Service management is exposed via the library client (`add_service` /
> `update_service` / `delete_service`).

## Library

```python
from exoscale_connector import ExoscaleClient
from exoscale_connector.resources.load_balancer import LoadBalancerClient

lbs = LoadBalancerClient(ExoscaleClient.from_env(zone="de-fra-1"))

# Create the LB
lb = lbs.create({"name": "web-lb", "description": "public web LB"})

# Add a service pointing at a pool. Use a dict payload — the model currently
# flattens healthcheck fields and lacks instance-pool, so dicts are the more
# faithful API exercise.
lbs.add_service(lb.id, {
    "name": "http",
    "protocol": "tcp",
    "port": 80,
    "target-port": 80,
    "strategy": "round-robin",
    "instance-pool": {"id": "<pool-id>"},
    "healthcheck": {"mode": "tcp", "port": 80, "interval": 10, "timeout": 5, "retries": 2},
})

# Update — must send the full service spec; PUT is a replace, not a patch
lbs.update_service(lb.id, service_id, {
    "name": "http", "protocol": "tcp", "port": 80, "target-port": 80,
    "strategy": "round-robin", "instance-pool": {"id": "<pool-id>"},
    "healthcheck": {"mode": "tcp", "port": 80, "interval": 20, "timeout": 5, "retries": 2},
})

lbs.delete_service(lb.id, service_id)
lbs.delete(lb.id)
```

## Gotchas

- **`update_service` is a FULL-RESOURCE PUT**, not a partial PATCH. Sending
  only the field you want to change is rejected by the API with a
  confusing error (the server tries to default missing required fields
  from the request line itself — yielding `"HTTP/1.1"` as the value at
  `protocol`). Always resend the full service spec on update.
- **Service needs a backing `instance-pool`** with `{"id": ...}`. Pointing
  at individual instances isn't supported.
- **Service path is `/service` (singular)**, e.g.
  `POST /load-balancer/<id>/service`. The agent verified this against the
  production playbook and it's not always reflected in the OpenAPI index.
- **The `LoadBalancerService` model currently flattens healthcheck fields
  and lacks an `instance_pool` field.** Use dict payloads to send the full
  spec the wire expects. (Tracked as a follow-up model refinement.)
- **Delete the LB before deleting the backing pool** — the API rejects
  deleting a pool that has an LB pointing at it.

## End-to-end example

Distilled from
[`tests/integration/test_tier_4.py::test_load_balancer_lifecycle`](../../tests/integration/test_tier_4.py):

```python
from exoscale_connector import ExoscaleClient
from exoscale_connector.resources.instance_pool import InstancePoolClient
from exoscale_connector.resources.load_balancer import LoadBalancerClient
from tests.integration._fixtures import (
    resolve_instance_type, resolve_linux_template, wait_for_state,
)

client = ExoscaleClient.from_env(zone="de-fra-1")
pools = InstancePoolClient(client)
lbs = LoadBalancerClient(client)

# 1. Backing pool
pool = pools.create({
    "name": "lb-pool",
    "size": 1,
    "instance-type": {"id": resolve_instance_type(client, "standard.tiny")},
    "template": {"id": resolve_linux_template(client)},
    "disk-size": 10,
})
wait_for_state(lambda: pools.get(pool.id), "running", timeout=600)

# 2. Load balancer
lb = lbs.create({"name": "demo-lb", "description": "demo"})
wait_for_state(lambda: lbs.get(lb.id), "running", timeout=300)

# 3. Service
svc_payload = {
    "name": "http", "protocol": "tcp", "port": 80, "target-port": 80,
    "strategy": "round-robin", "instance-pool": {"id": pool.id},
    "healthcheck": {"mode": "tcp", "port": 80, "interval": 10, "timeout": 5, "retries": 2},
}
lbs.add_service(lb.id, svc_payload)
svc = next(s for s in lbs.get(lb.id).services if s.name == "http")

# 4. Update (full-spec replace)
lbs.update_service(lb.id, svc.id, {**svc_payload,
    "healthcheck": {**svc_payload["healthcheck"], "interval": 20},
})

# 5. Cleanup in order: service -> LB -> pool
lbs.delete_service(lb.id, svc.id)
lbs.delete(lb.id)
pools.delete(pool.id)
```
