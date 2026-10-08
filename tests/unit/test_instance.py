"""Unit tests for InstanceClient."""

from __future__ import annotations

import responses

from exoscale_connector.resources.instance import InstanceClient


@responses.activate
def test_list_parses_typed_models(client, base_url) -> None:
    responses.add(
        responses.GET,
        f"{base_url}/instance",
        json={
            "instances": [
                {"id": "i-1", "name": "web-01", "state": "running"},
                {"id": "i-2", "name": "web-02", "state": "stopped"},
            ]
        },
        status=200,
    )
    instances = InstanceClient(client).list()
    assert [i.name for i in instances] == ["web-01", "web-02"]
    assert instances[0].state == "running"


@responses.activate
def test_get_parses_references(client, base_url) -> None:
    responses.add(
        responses.GET,
        f"{base_url}/instance/i-1",
        json={
            "id": "i-1",
            "name": "web-01",
            "state": "running",
            "instance-type": {"id": "type-uuid"},
            "template": {"id": "tmpl-uuid"},
            "security-groups": [{"id": "sg-1"}, {"id": "sg-2"}],
            "disk-size": 50,
            "public-ip": "1.2.3.4",
        },
        status=200,
    )
    inst = InstanceClient(client).get("i-1")
    assert inst.id == "i-1"
    assert inst.instance_type is not None and inst.instance_type.id == "type-uuid"
    assert inst.template is not None and inst.template.id == "tmpl-uuid"
    assert inst.disk_size == 50
    assert inst.public_ip == "1.2.3.4"
    assert len(inst.security_groups) == 2


@responses.activate
def test_find_by_name_case_insensitive(client, base_url) -> None:
    responses.add(
        responses.GET,
        f"{base_url}/instance",
        json={"instances": [{"id": "i-1", "name": "web-01"}]},
        status=200,
    )
    found = InstanceClient(client).find_by_name("WEB-01")
    assert found is not None and found.id == "i-1"


@responses.activate
def test_create_awaits_operation_and_refetches(client, base_url) -> None:
    responses.add(
        responses.POST,
        f"{base_url}/instance",
        json={"id": "op1", "state": "success", "reference": {"id": "i-new"}},
        status=200,
    )
    responses.add(
        responses.GET,
        f"{base_url}/instance/i-new",
        json={"id": "i-new", "name": "web-03", "state": "running"},
        status=200,
    )
    created = InstanceClient(client).create({"name": "web-03"})
    assert created.id == "i-new"
    assert created.name == "web-03"


@responses.activate
def test_delete_returns_settled_operation(client, base_url) -> None:
    responses.add(
        responses.DELETE,
        f"{base_url}/instance/i-1",
        json={"id": "op9", "state": "pending"},
        status=200,
    )
    responses.add(
        responses.GET,
        f"{base_url}/operation/op9",
        json={"id": "op9", "state": "success"},
        status=200,
    )
    op = InstanceClient(client).delete("i-1")
    assert op.state == "success"


@responses.activate
def test_start_puts_colon_action(client, base_url) -> None:
    responses.add(
        responses.PUT,
        f"{base_url}/instance/i-1:start",
        json={"id": "op-start", "state": "success"},
        status=200,
    )
    op = InstanceClient(client).start("i-1")
    assert op.state == "success"
    assert responses.calls[0].request.method == "PUT"


@responses.activate
def test_stop_puts_colon_action(client, base_url) -> None:
    responses.add(
        responses.PUT,
        f"{base_url}/instance/i-1:stop",
        json={"id": "op-stop", "state": "pending"},
        status=200,
    )
    responses.add(
        responses.GET,
        f"{base_url}/operation/op-stop",
        json={"id": "op-stop", "state": "success"},
        status=200,
    )
    op = InstanceClient(client).stop("i-1")
    assert op.state == "success"


@responses.activate
def test_reboot_puts_colon_action(client, base_url) -> None:
    responses.add(
        responses.PUT,
        f"{base_url}/instance/i-1:reboot",
        json={"id": "op-reboot", "state": "success"},
        status=200,
    )
    op = InstanceClient(client).reboot("i-1")
    assert op.id == "op-reboot"


@responses.activate
def test_get_parses_deploy_target_reference(client, base_url) -> None:
    responses.add(
        responses.GET,
        f"{base_url}/instance/i1",
        json={"id": "i1", "name": "vm", "deploy-target": {"id": "dt1"}},
        status=200,
    )
    instance = InstanceClient(client).get("i1")
    assert instance.deploy_target is not None
    assert instance.deploy_target.id == "dt1"


def test_instance_parses_attachment_and_security_fields() -> None:
    from exoscale_connector.resources.instance import Instance

    inst = Instance.model_validate(
        {
            "id": "i-1",
            "anti-affinity-groups": [{"id": "aag-1"}],
            "elastic-ips": [{"id": "eip-1"}],
            "private-networks": [{"id": "pn-1", "mac-address": "aa:bb:cc:dd:ee:ff"}],
            "ssh-keys": [{"name": "ops"}, {"name": "ci"}],
            "user-data": "I2Nsb3VkLWNvbmZpZw==",
            "public-ip-assignment": "dual",
            "mac-address": "11:22:33:44:55:66",
            "disk-encrypted": True,
            "secureboot-enabled": False,
            "tpm-enabled": True,
        }
    )
    assert [a.id for a in inst.anti_affinity_groups] == ["aag-1"]
    assert inst.elastic_ips[0].id == "eip-1"
    assert inst.private_networks[0].mac_address == "aa:bb:cc:dd:ee:ff"
    assert [k.name for k in inst.ssh_keys] == ["ops", "ci"]
    assert inst.public_ip_assignment == "dual"
    assert (inst.disk_encrypted, inst.secureboot_enabled, inst.tpm_enabled) == (True, False, True)


def test_instance_without_new_fields_serialises_without_them() -> None:
    from exoscale_connector.resources.instance import Instance

    payload = Instance(name="web").to_api_payload()
    assert "elastic-ips" not in payload and "ssh-keys" not in payload
