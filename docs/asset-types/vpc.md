# vpc (+ subnets, routes)

A **VPC** (Virtual Private Cloud) is a private network fabric with its own
routing domain. It owns **subnets** (IP ranges instances attach to) and, per
subnet, **routes**. Instances join a subnet via attach/detach.

## Model

```python
class Vpc(ExoscaleModel):
    id: Optional[str]
    name: Optional[str]
    description: Optional[str]
    labels: Optional[Dict[str, str]]
    created_at: Optional[str]


class VpcSubnet(ExoscaleModel):
    id: Optional[str]
    name: Optional[str]
    description: Optional[str]
    address_space: Optional[str]    # "private"
    addressfamily: Optional[str]    # "inet4" | "dual"
    ipv4_block: Optional[str]       # CIDR
    labels: Optional[Dict[str, str]]
    created_at: Optional[str]


class VpcRoute(ExoscaleModel):
    id: Optional[str]
    description: Optional[str]
    destination: Optional[str]      # CIDR the route matches
    target: Optional[str]           # next-hop
    kind: Optional[str]             # "Subnet" | "Vpc"
```

## CLI

The umbrella CLI exposes VPC CRUD and subnet management (`<verb>-vpc` /
`<verb>-subnet`). Routes and instance attach/detach are one level deeper and are
library-only.

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

# VPC CRUD (async, awaited by default)
op = vpc.create({"name": "prod", "description": "prod fabric"})
vpc_id = op.reference_id

# Subnets
vpc.create_subnet(vpc_id, {
    "name": "app",
    "addressfamily": "inet4",
    "address-space": "private",
    "ipv4-block": "10.0.0.0/24",
})
subnets = vpc.list_subnets(vpc_id)
subnet_id = subnets[0].id

# Attach / detach an instance to a subnet
vpc.attach_subnet(vpc_id, subnet_id, instance_id)
vpc.detach_subnet(vpc_id, subnet_id, instance_id)

# Routes (per subnet)
vpc.create_route(vpc_id, subnet_id, {"destination": "0.0.0.0/0", "target": "10.0.0.1"})
routes = vpc.list_subnet_routes(vpc_id, subnet_id)
all_routes = vpc.list_routes(vpc_id)          # every route in the VPC
vpc.delete_route(vpc_id, subnet_id, routes[0].id)

# Teardown
vpc.delete_subnet(vpc_id, subnet_id)
vpc.delete(vpc_id)
```

## Gotchas

- **Subnet create requires three fields:** `name`, `addressfamily`
  (`inet4`/`dual`), and `address-space` (`private`). Set the CIDR with
  `ipv4-block`.
- **Instance membership lives on the subnet.** Join with
  `attach_subnet(vpc_id, subnet_id, instance_id)` (wraps
  `PUT vpc/{vpc}/subnet/{subnet}/attach` with `{"instance": {"id": ...}}`), not
  the instance's own update endpoint. Attach/detach are async, awaited by default.
- **Routes belong to a subnet, not the VPC directly.** Create/delete a route
  under a subnet; `list_routes(vpc_id)` returns the union across all subnets for
  a fabric-wide view.
- **Do not send `name` when creating a route.** The `name` request property was
  dropped upstream; a route is identified by its `destination`/`target`.
- **VPC create is async.** `create` returns the operation; the new VPC id is on
  `operation.reference_id` once it settles (awaited by default).
