"""Unit tests for the umbrella CLI and table output."""

from __future__ import annotations

import pytest

from exoscale_connector.cli._base import render_table
from exoscale_connector.cli.main import main as umbrella_main
from exoscale_connector.resources.security_group import SecurityGroup, SecurityGroupClient
from exoscale_connector.resources.zone import Zone, ZoneClient


@pytest.fixture(autouse=True)
def cli_env(monkeypatch) -> None:
    monkeypatch.setenv("EXOSCALE_API_KEY", "EXOtestkey")
    monkeypatch.setenv("EXOSCALE_API_SECRET", "testsecret")
    monkeypatch.setenv("EXOSCALE_ZONE", "de-fra-1")


def test_umbrella_dispatches_to_asset_cli(monkeypatch, capsys) -> None:
    monkeypatch.setattr(ZoneClient, "list", lambda self, **kw: [Zone(name="de-fra-1")])
    assert umbrella_main(["zone", "list-zones"]) == 0
    assert "de-fra-1" in capsys.readouterr().out


def test_umbrella_unknown_asset_exits_2(capsys) -> None:
    assert umbrella_main(["does-not-exist"]) == 2
    err = capsys.readouterr().err
    assert "unknown asset" in err and "security-group" in err


def test_umbrella_no_args_prints_usage_exit_2(capsys) -> None:
    assert umbrella_main([]) == 2
    assert "usage:" in capsys.readouterr().err


def test_umbrella_help_exits_0(capsys) -> None:
    assert umbrella_main(["--help"]) == 0
    assert "assets:" in capsys.readouterr().out


def test_umbrella_version(capsys) -> None:
    assert umbrella_main(["--version"]) == 0
    assert "exoscale-connector" in capsys.readouterr().out


def test_output_table_via_harness(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        SecurityGroupClient,
        "list",
        lambda self, **kw: [
            SecurityGroup(id="sg-1", name="web"),
            SecurityGroup(id="sg-2", name="db"),
        ],
    )
    assert umbrella_main(["security-group", "--output", "table", "list"]) == 0
    out = capsys.readouterr().out
    lines = out.splitlines()
    # rules defaults to [] (not None) so it survives exclude_none and gets a column
    assert lines[0].split() == ["id", "name", "rules"]
    assert "sg-1" in lines[2] and "web" in lines[2]


def test_render_table_union_of_columns() -> None:
    rendered = render_table([{"a": 1}, {"a": 2, "b": "x"}])
    lines = rendered.splitlines()
    assert lines[0].split() == ["a", "b"]
    assert lines[2].split() == ["1"]  # missing cell renders empty
    assert lines[3].split() == ["2", "x"]


def test_render_table_single_dict_becomes_key_value() -> None:
    rendered = render_table({"name": "web", "exists": True})
    assert rendered.splitlines()[0].split() == ["field", "value"]
    assert "exists" in rendered


def test_render_table_nested_values_compact_json() -> None:
    rendered = render_table([{"name": "web", "labels": {"env": "prod"}}])
    assert '{"env":"prod"}' in rendered


def test_render_table_non_dict_falls_back_to_json() -> None:
    assert render_table(["just", "strings"]) == '[\n  "just",\n  "strings"\n]'
