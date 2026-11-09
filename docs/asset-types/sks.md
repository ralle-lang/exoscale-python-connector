# sks (cluster + nodepool + kubeconfig)

Exoscale Kubernetes Service. A cluster (`SksCluster`) owns one or more
nodepools (`SksNodepool`) as sub-resources. Worker nodes are real compute
instances spun up by Exoscale's control plane.

## Model

```python
class SksNodepoolTaint(ExoscaleModel):
    value: Optional[str]
    effect: Optional[str]                        # "NoExecute" | "NoSchedule" | "PreferNoSchedule"


class SksNodepool(ExoscaleModel):
    id: Optional[str]
    name: Optional[str]
    description: Optional[str]
    size: Optional[int]                          # number of worker nodes
    state: Optional[str]
    instance_type: Optional[Reference]
    template: Optional[Reference]
    instance_pool: Optional[Reference]           # auto-created pool managing the nodes
    disk_size: Optional[int]                     # GiB
    security_groups: Optional[List[Reference]]
    anti_affinity_groups: Optional[List[Reference]]
    private_networks: Optional[List[Reference]]
    labels: Optional[Dict[str, str]]
    taints: Optional[Dict[str, SksNodepoolTaint]]  # keyed by taint key
    instance_prefix: Optional[str]
    public_ip_assignment: Optional[str]
    nvidia_mig_profiles: Optional[Dict[str, Any]]  # MIG profiles for GPU nodes, keyed by GPU model
    deploy_target: Optional[Reference]           # dedicated / edge placement
    kubelet_image_gc: Optional[SksKubeletImageGc]  # high_threshold, low_threshold, min_age


class SksCluster(ExoscaleModel):
    id: Optional[str]
    name: Optional[str]
    description: Optional[str]
    state: Optional[str]
    version: Optional[str]                       # Kubernetes version
    endpoint: Optional[str]                      # control-plane API URL
    cni: Optional[str]                           # "calico" | "cilium"
    service_level: Optional[str]                 # "starter" | "pro"; wire field `level`
    addons: Optional[List[str]]
    labels: Optional[Dict[str, str]]
    auto_upgrade: Optional[bool]
    created_at: Optional[str]
    nodepools: Optional[List[SksNodepool]]       # embedded in detail responses
    oidc: Optional[SksOidc]                      # API-server OpenID Connect
    feature_gates: Optional[List[str]]           # Kubernetes alpha feature gates
    enable_kube_proxy: Optional[bool]
    default_security_group_id: Optional[str]     # read-only


class SksOidc(ExoscaleModel):
    client_id: Optional[str]                     # required with issuer_url
    issuer_url: Optional[str]
    username_claim: Optional[str]
    username_prefix: Optional[str]
    groups_claim: Optional[str]
    groups_prefix: Optional[str]
    required_claim: Optional[Dict[str, str]]
```

## Addons

Addons are optional components Exoscale installs into the cluster (or nodepool).
Enable them by passing `addons: [...]` at create. The valid values below are
**generated from the committed OpenAPI spec** and kept current by the upstream
drift watch — don't hand-edit them. Notably,
`exoscale-container-storage-interface` installs the Exoscale CSI driver needed
for block-volume-backed PersistentVolumeClaims.

<!-- BEGIN GENERATED:sks-addons -->
<!-- Generated from .github/upstream/openapi-v2.json by scripts/generate_llms_txt.py — do not edit by hand. -->
- **Cluster** (`SksCluster.addons`): `exoscale-cloud-controller`, `exoscale-container-storage-interface`, `metrics-server`, `karpenter`
- **Nodepool** (`SksNodepool.addons`): `storage-lvm`
<!-- END GENERATED:sks-addons -->

## CLI

```bash
exoscale-sks list-clusters
exoscale-sks get-cluster --id <uuid>
exoscale-sks create-cluster --json '{"name":"prod-k8s","level":"starter","cni":"calico","version":"1.30"}'
exoscale-sks delete-cluster --id <uuid>

exoscale-sks list-nodepools --cluster-id <uuid>
exoscale-sks create-nodepool --cluster-id <uuid> --json '{"name":"workers","size":1,"instance-type":{"id":"<type-id>"},"disk-size":20}'
exoscale-sks delete-nodepool --cluster-id <uuid> --id <uuid>
```

## Library

```python
from exoscale_connector import ExoscaleClient
from exoscale_connector.resources.sks import SksClusterClient, SksNodepool

sks = SksClusterClient(ExoscaleClient.from_env(zone="de-fra-1"))

# Discover valid Kubernetes versions instead of hardcoding one — the accepted
# set changes as Exoscale adds/retires releases. The API returns them
# newest-first, so [0] is the latest.
versions = sks.list_versions()        # e.g. ["1.31.0", "1.30.4", ...]

# Cluster
cluster = sks.create({
    "name": "prod-k8s",
    "description": "production cluster",
    "version": versions[0],            # latest; or pick a specific supported one
    "cni": "calico",
    "level": "starter",            # field is "level", not "service-level"
})

# Kubeconfig — both `user` and `groups` are required
kubeconfig = sks.generate_kubeconfig(cluster.id, {
    "user": "admin",
    "groups": ["system:masters"],
})

# Nodepool
op = sks.create_nodepool(cluster.id, SksNodepool(
    name="workers",
    size=1,
    instance_type={"id": "<type-id>"},
    disk_size=20,
))
np_id = op.reference_id

# Scale, or remove specific nodes (member ids from the nodepool's instance pool)
sks.scale_nodepool(cluster.id, np_id, 3)
sks.evict_nodepool_members(cluster.id, np_id, ["<member-instance-id>"])

# Cluster reads: CA certificates, diagnostic report, Karpenter manifests
ca = sks.get_authority_cert(cluster.id, "control-plane")   # or aggregation / kubelet
report = sks.get_inspection(cluster.id)     # last report (dict) or None if none ran yet
nodeclass = sks.generate_karpenter_nodeclass(cluster.id)    # manifest str
karpenter_np = sks.generate_karpenter_nodepool(cluster.id)

# Credential rotation (async; the cluster stays up)
sks.rotate_ccm_credentials(cluster.id)
sks.rotate_csi_credentials(cluster.id)
sks.rotate_karpenter_credentials(cluster.id)
sks.rotate_operators_ca(cluster.id)

# Before a version upgrade: which Kubernetes APIs in use does a later release
# remove? Migrate anything whose removed_release <= the target version first.
for r in sks.list_deprecated_resources(cluster.id):
    print(r.group, r.version, r.resource, "removed in", r.removed_release)

# Upgrade the control plane, or move starter -> pro (one-way, billed)
sks.upgrade(cluster.id, "<newer version from list_versions()>")
sks.upgrade_service_level(cluster.id)

# Cleanup (nodepool first, then cluster)
sks.delete_nodepool(cluster.id, np_id)
sks.delete(cluster.id)
```

## Gotchas

- **`list_deprecated_resources()` is pending live verification** (implemented
  from the API reference). It is read-only and safe to call at any time.
- **Don't hardcode the Kubernetes `version` — discover it.** Call
  `list_versions()` (wraps `GET /sks-cluster-version`) and pick from the
  returned list. The accepted set shifts over time as Exoscale ships new
  Kubernetes releases and retires old ones, so a literal like `"1.30"` that
  works today can later be rejected at create. The list is newest-first.
- **Cluster create field is `level`, not `service-level`.** An initial test
  payload used `service-level` and the API responded with
  `400: missing keys 'level'`. Allowed values: `starter` (free control
  plane) or `pro` (paid SLA). The model attribute is `service_level`, mapped to the
  `level` wire field in both directions (`SksCluster(level=...)` works too).
- **Kubeconfig requires `user` AND `groups`** in the request body.
  `groups` is a list of Kubernetes groups (e.g. `["system:masters"]` for
  cluster-admin). Missing `groups` returns `400: missing keys 'groups'`.
- **Nodepool needs `standard.small` or larger** if you want to attach
  block-storage volumes (same constraint as raw instances).
- **Cluster provisioning takes ~5–10 min**; nodepool another few minutes;
  scale operations ~1 min per added node. Use generous timeouts.
- **`list_nodepools` reads from the cluster detail's embedded
  `nodepools` array** — there is no standalone nodepool list endpoint.
- **Cluster delete cascades to nodepools and member instances.** Wait for
  the delete to complete before reusing names.
- **`generate_kubeconfig` endpoint** is at the top level
  `POST /sks-cluster-kubeconfig/<id>`, not nested under
  `sks-cluster/<id>/...`.
- **`create_nodepool` returns an `Operation`, not the nodepool.** This
  breaks the otherwise-uniform "create returns the resource" contract,
  but it is deliberate: the API has no standalone nodepool list/get
  endpoint — nodepools are only visible embedded in the cluster's detail
  response. Use `op.reference_id` and then read the nodepool out of the
  cluster's `nodepools` array (or `list_nodepools(cluster_id)` which
  does exactly that).
- **`upgrade` moves the control plane only.** `PUT sks-cluster/{id}/upgrade`
  takes a version from `list_versions()`; check `list_deprecated_resources`
  first. Existing nodes keep their version until they are replaced.
- **`upgrade_service_level` is one-way.** It moves `starter` to `pro`, there
  is no downgrade endpoint, and `pro` is billed.
- **`scale_nodepool` vs `evict_nodepool_members`.** Scaling down lets the API
  choose which nodes go; evict drains and destroys exactly the instances you
  name (members of the nodepool's `instance_pool`) and shrinks the size to
  match.
- **Credential rotation needs the matching addon.** `rotate_ccm_credentials`
  on a cluster without `exoscale-cloud-controller` fails with
  `405 Cluster without exoscale-cloud-controller addon enabled` (observed
  live). Likewise, CSI rotation needs `exoscale-container-storage-interface`
  and the Karpenter calls need `karpenter`.
- **The `karpenter` addon needs a pro cluster.** Creating a `starter` cluster
  with it fails with `403 A PRO cluster is required`. Upgrade with
  `upgrade_service_level`, then add it through `update` (`addons` is
  updatable).

## End-to-end example

Distilled from
[`tests/integration/test_tier_4.py::test_sks_lifecycle`](../../tests/integration/test_tier_4.py):

```python
import time
from exoscale_connector import ExoscaleClient
from exoscale_connector.resources.sks import SksClusterClient, SksNodepool
from tests.integration._fixtures import (
    resolve_instance_type, resolve_sks_version, wait_for_state,
)

client = ExoscaleClient.from_env(zone="de-fra-1")
sks = SksClusterClient(client)

# 1. Cluster (cheapest service level + smallest version)
cluster = sks.create({
    "name": "demo-cluster",
    "version": resolve_sks_version(client),
    "cni": "calico",
    "level": "starter",
})
wait_for_state(lambda: sks.get(cluster.id), "running", timeout=1200, interval=15)

# 2. Kubeconfig — never print the contents in real code
kubeconfig = sks.generate_kubeconfig(cluster.id, {
    "user": "demo-admin",
    "groups": ["system:masters"],
})
assert kubeconfig  # contains a base64 kubeconfig blob

# 3. Nodepool (size=1, standard.small)
np_op = sks.create_nodepool(cluster.id, SksNodepool(
    name="workers",
    size=1,
    instance_type={"id": resolve_instance_type(client, "standard.small")},
    disk_size=20,
))
np_id = np_op.reference_id

# Poll the cluster's embedded nodepool list until the node is running
deadline = time.time() + 1200
while time.time() < deadline:
    c = sks.get(cluster.id)
    np = next((n for n in (c.nodepools or []) if n.id == np_id), None)
    if np and (np.state or "").lower() == "running":
        break
    time.sleep(15)

# 4. Scale 1 -> 2 -> 1
sks.update_nodepool(cluster.id, np_id, {"size": 2})
sks.update_nodepool(cluster.id, np_id, {"size": 1})

# 5. Cleanup (nodepool first)
sks.delete_nodepool(cluster.id, np_id)
sks.delete(cluster.id)
```
