"""Tests for the ``exoscale-connector skill`` CLI."""
from pathlib import Path

from exoscale_connector.cli import skill
from exoscale_connector.cli.main import main as umbrella_main


def test_packaged_skill_dir_ships_both_files():
    source = skill.packaged_skill_dir()
    for name in skill.SKILL_FILES:
        assert (source / name).is_file(), f"{name} missing from packaged skill"


def test_install_into_project_dir(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    assert skill.main(["install"]) == 0
    dest = tmp_path / ".claude" / "skills" / "exoscale-connector"
    source = skill.packaged_skill_dir()
    for name in skill.SKILL_FILES:
        assert (dest / name).read_text(encoding="utf-8") == (source / name).read_text(
            encoding="utf-8"
        )
    assert "installed" in capsys.readouterr().out


def test_install_user_level(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    assert skill.main(["install", "--user"]) == 0
    assert (tmp_path / ".claude" / "skills" / "exoscale-connector" / "SKILL.md").is_file()


def test_install_custom_dest_and_reinstall_refreshes(tmp_path):
    dest = tmp_path / "anywhere"
    assert skill.main(["install", "--dest", str(dest)]) == 0
    (dest / "SKILL.md").write_text("stale", encoding="utf-8")
    assert skill.main(["install", "--dest", str(dest)]) == 0
    assert (dest / "SKILL.md").read_text(encoding="utf-8") != "stale"


def test_path_verb_prints_existing_dir(capsys):
    assert skill.main(["path"]) == 0
    printed = Path(capsys.readouterr().out.strip())
    assert printed.is_dir()


def test_umbrella_dispatches_skill(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert umbrella_main(["skill", "install"]) == 0
    assert (tmp_path / ".claude" / "skills" / "exoscale-connector" / "reference.md").is_file()


def test_umbrella_usage_mentions_skill(capsys):
    assert umbrella_main(["--help"]) == 0
    assert "skill" in capsys.readouterr().out
