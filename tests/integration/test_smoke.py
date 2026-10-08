"""Read-only live smoke tests (opt-in; see conftest for how to enable).

These exercise every asset-type client against a real account using only
``list`` (read-only), so they are safe to run against any environment. They
prove the things unit tests cannot: that request signing works, that the
per-zone endpoints are correct, and that each collection path + list key +
model actually matches what the API returns. They never create, modify or
delete anything.
"""

from __future__ import annotations

import pytest

from exoscale_connector.errors import APIError
from exoscale_connector.resources.anti_affinity_group import AntiAffinityGroupClient
from exoscale_connector.resources.api_key import ApiKeyClient
from exoscale_connector.resources.block_volume import BlockVolumeClient
from exoscale_connector.resources.block_volume_snapshot import BlockVolumeSnapshotClient
from exoscale_connector.resources.dbaas import DBaaSServiceClient
from exoscale_connector.resources.deploy_target import DeployTargetClient
from exoscale_connector.resources.dns import DnsDomainClient
from exoscale_connector.resources.elastic_ip import ElasticIPClient
from exoscale_connector.resources.event import EventClient
from exoscale_connector.resources.iam_role import IAMRoleClient
from exoscale_connector.resources.iam_user import IAMUserClient
from exoscale_connector.resources.instance import InstanceClient
from exoscale_connector.resources.instance_pool import InstancePoolClient
from exoscale_connector.resources.kms import KmsKeyClient
from exoscale_connector.resources.load_balancer import LoadBalancerClient
from exoscale_connector.resources.private_network import PrivateNetworkClient
from exoscale_connector.resources.security_group import SecurityGroupClient
from exoscale_connector.resources.sks import SksClusterClient
from exoscale_connector.resources.snapshot import SnapshotClient
from exoscale_connector.resources.ssh_key import SSHKeyClient
from exoscale_connector.resources.vpc import VpcClient

pytestmark = pytest.mark.integration

# Every APIv2 asset-type client, exercised through its read-only ``list`` verb.
READ_ONLY_CLIENTS = [
    ("security-group", SecurityGroupClient),
    ("elastic-ip", ElasticIPClient),
    ("private-network", PrivateNetworkClient),
    ("load-balancer", LoadBalancerClient),
    ("vpc", VpcClient),
    ("deploy-target", DeployTargetClient),
    ("event", EventClient),
    ("instance", InstanceClient),
    ("instance-pool", InstancePoolClient),
    ("anti-affinity-group", AntiAffinityGroupClient),
    ("snapshot", SnapshotClient),
    ("block-volume", BlockVolumeClient),
    ("block-volume-snapshot", BlockVolumeSnapshotClient),
    ("api-key", ApiKeyClient),
    ("iam-role", IAMRoleClient),
    ("iam-user", IAMUserClient),
    ("ssh-key", SSHKeyClient),
    ("kms", KmsKeyClient),
    ("dns-domain", DnsDomainClient),
    ("dbaas", DBaaSServiceClient),
    ("sks-cluster", SksClusterClient),
]


@pytest.mark.parametrize(
    "label,client_cls",
    READ_ONLY_CLIENTS,
    ids=[label for label, _ in READ_ONLY_CLIENTS],
)
def test_list_is_reachable(live_client, label, client_cls) -> None:
    """Listing each asset type against a real zone must succeed and return a list."""
    try:
        items = client_cls(live_client).list()
    except APIError as exc:
        # A 403 on a read-only list is a tenant/credential capability gate, not a
        # connector fault: signing worked and the endpoint was reached, only
        # authorization was refused — e.g. VPC "... not enabled" on accounts
        # without it, or "Forbidden by role policy for kms" when the API key's
        # IAM role doesn't grant that product. Skip rather than fail.
        if exc.status_code == 403:
            pytest.skip(f"{label}: forbidden on this tenant/credential ({exc})")
        raise
    assert isinstance(items, list)


def test_iam_user_get_resolves_existing_user(live_client) -> None:
    """APIv2 has no GET /user/{id}; get() must still find a listed user."""
    users = IAMUserClient(live_client)
    listed = users.list()
    if not listed:
        pytest.skip("no IAM users on this tenant")
    assert users.get(listed[0].id).id == listed[0].id


def test_object_storage_list_is_reachable(live_client) -> None:
    """Object Storage uses the S3 (boto3) path; skip if boto3 isn't installed."""
    pytest.importorskip("boto3")
    from exoscale_connector.resources.object_storage import BucketClient

    buckets = BucketClient(live_client.config).list()
    assert isinstance(buckets, list)


# ---------------------------------------------------------------------------- #
# Platform catalogues (zones / templates / instance types) — read-only.
# ---------------------------------------------------------------------------- #


def test_list_zones(live_client) -> None:
    from exoscale_connector.resources.zone import ZoneClient

    zones = ZoneClient(live_client).list()
    assert zones, "zone list came back empty"
    assert any(z.name for z in zones)


def test_list_templates_and_find_linux(live_client) -> None:
    from exoscale_connector.resources.template import TemplateClient

    templates = TemplateClient(live_client)
    public = templates.list(visibility="public")
    assert public, "no public templates returned"
    linux = templates.find_linux()
    assert linux is not None and linux.id, "find_linux found nothing"


def test_list_instance_types_and_find_slug(live_client) -> None:
    from exoscale_connector.resources.instance_type import InstanceTypeClient

    types = InstanceTypeClient(live_client)
    listed = types.list()
    assert listed, "instance-type list came back empty"
    tiny = types.find("standard.tiny")
    assert tiny is not None and tiny.id, "standard.tiny not resolvable"


def test_list_sks_versions(live_client) -> None:
    """SksClusterClient.list_versions() returns the live, non-empty version set.

    Read-only, so it lives with the smoke suite rather than the expensive SKS
    tier. Grounds the connector's version discovery against what the API
    actually accepts instead of a hardcoded literal.
    """
    versions = SksClusterClient(live_client).list_versions()
    assert isinstance(versions, list) and versions, "no SKS versions returned"
    assert all(isinstance(v, str) and v for v in versions)


# ---------------------------------------------------------------------------- #
# 0.7.0 tier-A reads — skip when the tenant has nothing to read or forbids it.
# ---------------------------------------------------------------------------- #


def _skip_if_forbidden(label, call):
    try:
        return call()
    except APIError as exc:
        if exc.status_code == 403:
            pytest.skip(f"{label}: forbidden on this tenant/credential ({exc})")
        raise


def test_dbaas_ca_certificate_is_pem(live_client) -> None:
    pem = _skip_if_forbidden(
        "dbaas-ca-certificate", DBaaSServiceClient(live_client).get_ca_certificate
    )
    assert pem.startswith("-----BEGIN CERTIFICATE-----")


def test_dbaas_logs_and_metrics_are_readable(live_client) -> None:
    dbaas = DBaaSServiceClient(live_client)
    services = dbaas.list()
    if not services:
        pytest.skip("no DBaaS services on this tenant")
    name = services[0].name
    page = _skip_if_forbidden("dbaas-service-logs", lambda: dbaas.get_logs(name, limit=1))
    assert isinstance(page.logs or [], list)
    metrics = _skip_if_forbidden(
        "dbaas-service-metrics", lambda: dbaas.get_metrics(name, period="hour")
    )
    assert isinstance(metrics, dict)


def test_sks_deprecated_resources_is_readable(live_client) -> None:
    sks = SksClusterClient(live_client)
    clusters = sks.list()
    if not clusters:
        pytest.skip("no SKS clusters on this tenant")
    found = sks.list_deprecated_resources(clusters[0].id)
    assert isinstance(found, list)


def test_iam_organization_policy_is_readable(live_client) -> None:
    policy = _skip_if_forbidden(
        "iam-organization-policy", IAMRoleClient(live_client).get_organization_policy
    )
    assert policy.default_service_strategy in ("allow", "deny")
