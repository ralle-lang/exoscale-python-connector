"""Unit tests for ResetFieldMixin and the load-balancer service reset/get."""

from __future__ import annotations

import pytest
import responses

from exoscale_connector.resources.elastic_ip import ElasticIPClient
from exoscale_connector.resources.instance import InstanceClient
from exoscale_connector.resources.instance_pool import InstancePoolClient
from exoscale_connector.resources.load_balancer import LoadBalancerClient
from exoscale_connector.resources.private_network import PrivateNetworkClient


@pytest.mark.parametrize(
    ("client_cls", "collection", "field"),
    [
        (InstanceClient, "instance", "labels"),
        (InstancePoolClient, "instance-pool", "description"),
        (ElasticIPClient, "elastic-ip", "description"),
        (PrivateNetworkClient, "private-network", "labels"),
        (LoadBalancerClient, "load-balancer", "labels"),
    ],
)
@responses.activate
def test_reset_field_deletes_the_field_path(client, base_url, client_cls, collection, field):
    responses.add(
        responses.DELETE,
        f"{base_url}/{collection}/r-1/{field}",
        json={"id": "op-1", "state": "success"},
        status=200,
    )
    op = client_cls(client).reset_field("r-1", field)
    assert op.state == "success"
    assert responses.calls[0].request.method == "DELETE"


@responses.activate
def test_reset_service_field(client, base_url):
    responses.add(
        responses.DELETE,
        f"{base_url}/load-balancer/lb-1/service/s-1/description",
        json={"id": "op-1", "state": "success"},
        status=200,
    )
    op = LoadBalancerClient(client).reset_service_field("lb-1", "s-1", "description")
    assert op.state == "success"


@responses.activate
def test_get_service_returns_typed_model(client, base_url):
    responses.add(
        responses.GET,
        f"{base_url}/load-balancer/lb-1/service/s-1",
        json={"id": "s-1", "name": "web", "port": 443, "target-port": 8443},
        status=200,
    )
    service = LoadBalancerClient(client).get_service("lb-1", "s-1")
    assert service.id == "s-1" and service.port == 443 and service.target_port == 8443
