# vpc (+ subnets, routes)

A **VPC** (Virtual Private Cloud) is a private network fabric with its own
routing domain. It owns **subnets** (IP ranges instances attach to) and, per
subnet, **routes**. Instances join a subnet via attach/detach.

VPC is a per-account product, and API keys need the IAM `networking` service
to use it. All 16 `/vpc` endpoints were verified live on 2026-11-02; see
[live test results](../live-test-results.md).

## Model

```python
class Vpc(ExoscaleModel):
    id: Optional[str]
    name: Optional[str]
    description: Optional[str]
    labels: Optional[Dict[str, str]]
    created_at: Optional[str]
    default: Optional[bool]         # returned live, not in the spec


class VpcSubnetInstance(ExoscaleModel):
    id: Optional[str]
    ipv4: Optional[str]


class VpcSubnet(ExoscaleModel):
    id: Optional[str]
    name: Optional[str]
    description: Optional[str]
    address_space: Optional[str]    # "private"
    addressfamily: Optional[str]    # create accepts "inet4" only
    ipv4_block: Optional[str]       # CIDR
    labels: Optional[Dict[str, str]]
    created_at: Optional[str]
    instances: Optional[List[VpcSubnetInstance]]   # attached instances + address


class VpcRoute(ExoscaleModel):
    id: Optional[str]
    description: Optional[str]
    destination: Optional[str]      # CIDR the route matches
    target: Optional[str]           # "ip=<next-hop>" (yours) | "cidr=<block>" (system)
    kind: Optional[str]             # "Subnet" (yours) | "Vpc" (system, read-only)
```

## CLI

The umbrella CLI exposes VPC list/get/create/delete and subnet
list/create/delete (`<verb>-vpc` / `<verb>-subnet`). VPC and subnet updates,
`get_subnet`, routes, and instance attach/detach are library-only.

```bash
exoscale-vpc list-vpcs
exoscale-vpc get-vpc --id <uuid>
exoscale-vpc create-vpc --json '{"name": "prod", "description": "prod fabric"}'
exoscale-vpc delete-vpc --id <uuid>

exoscale-vpc list-subnets --vpc-id <uuid>
exoscale-vpc create-subnet --vpc-id <uuid> \
  --json '{"name": "app", "addressfamily": "inet4", "address-space": "private", "ipv4-block": "10.0.0.0/24"}'
exoscale-vpc delete-subnet --vpc-id <uuid> --id <subnet-uuid>
```

## Library

```python
from exoscale_connector import ExoscaleClient
from exoscale_connector.resources.vpc import VpcClient

vpc = VpcClient(ExoscaleClient.from_env(zone="de-fra-1"))

# VPC CRUD — create/update return the settled Vpc model
created = vpc.create({"name": "prod", "description": "prod fabric"})
vpc_id = created.id
vpc.update(vpc_id, {"description": "prod fabric (eu)", "labels": {"env": "prod"}})

# Subnets
vpc.create_subnet(vpc_id, {
    "name": "app",
    "addressfamily": "inet4",
    "address-space": "private",
    "ipv4-block": "10.0.0.0/24",
})
subnet_id = vpc.list_subnets(vpc_id)[0].id
vpc.update_subnet(vpc_id, subnet_id, {"description": "app tier"})

# Attach / detach an instance; the subnet lists it with its leased address
vpc.attach_subnet(vpc_id, subnet_id, instance_id)
leases = {i.id: i.ipv4 for i in vpc.get_subnet(vpc_id, subnet_id).instances}
vpc.detach_subnet(vpc_id, subnet_id, instance_id)

# ... or pin the instance's address inside the subnet block
vpc.attach_subnet(vpc_id, subnet_id, instance_id, ipv4="10.0.0.42")

# Routes (per subnet); the next hop needs the "ip=" prefix
op = vpc.create_route(vpc_id, subnet_id, {"destination": "0.0.0.0/0", "target": "ip=10.0.0.10"})
routes = vpc.list_subnet_routes(vpc_id, subnet_id)   # yours + the system route
vpc.delete_route(vpc_id, subnet_id, op.reference_id)

# Teardown
vpc.delete_subnet(vpc_id, subnet_id)
vpc.delete(vpc_id)
```

## Gotchas

- **Route `target` is prefixed.** Write the next hop as `ip=<address>`
  (e.g. `ip=10.0.0.10`). A bare address, `cidr=…`, or an instance/subnet id is
  rejected with `400 Invalid value in target - bad format`. The spec only says
  "Route target". Live, the API also accepted a next hop outside the subnet's
  CIDR and a `0.0.0.0/0` destination.
- **Every subnet gets a system route.** It has `kind: "Vpc"`, the subnet's
  block as `destination`, and `target: "cidr=<block>"`. You cannot create or
  delete it; routes you add have `kind: "Subnet"`.
- **`list_routes(vpc_id)` returns only the system routes**, not the routes
  added with `create_route`. Use `list_subnet_routes(vpc_id, subnet_id)` to see
  a subnet's own routes (it returns the system route too).
- **Subnet create accepts `addressfamily: "inet4"` only.** `dual` is rejected
  with a 400. The response schema still lists it, so a read may report `dual`.
  Create also requires `name` and `address-space` (`private`); set the CIDR with
  `ipv4-block`.
- **Instance membership lives on the subnet.** Join with
  `attach_subnet(vpc_id, subnet_id, instance_id)` (wraps
  `PUT vpc/{vpc}/subnet/{subnet}/attach` with `{"instance": {"id": ...}}`), not
  the instance's own update endpoint. Pass `ipv4=` to pin a fixed address
  from the subnet block (sent as the optional `ipv4` body field); without it
  the API picks one. The subnet's `instances` list then names the instance and
  its address. The instance response
  also gains a `vpc` object (`id`, `name`, `subnets`), kept untyped and
  readable via `instance.model_extra["vpc"]`.
- **Do not send `name` when creating a route.** The request property was
  dropped upstream. The API still accepts and silently ignores it.
- **Async vs. sync, as observed live:**
  - **Async:** VPC create, subnet create, and attach/detach return operations,
    which are awaited by default.
  - **Sync, returning the resource:** VPC update, subnet update, and route
    create. The subnet and route calls still return an `Operation`, already
    settled (`state == "success"`, `reference_id` set to the resource id).
  - **Sync, empty body:** all three deletes (VPC, subnet, route). They also
    yield a settled `success` operation.
  - Nothing synchronous is polled.
- **`dhcp-options` is returned but untyped.** The VPC response carries
  `dhcp-options` (`dns-servers`, `ntp-servers`, `domain-search` lists). It is
  not in the spec, no request can set it, and a fresh VPC returns only empty
  lists, so the element types are unverified and it stays untyped (`vpc.model_extra["dhcp-options"]`).
