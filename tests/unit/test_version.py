"""The package version has a single source of truth.

``exoscale_connector.__version__`` is the one place the version is declared;
``pyproject.toml`` marks ``version`` as ``dynamic`` and resolves it from that
literal at build time (``[tool.hatch.version]``). Keeping the literal in the code
(rather than reading installed distribution metadata) means a *vendored* copy of
the package — copied into another repo, not pip-installed — still reports the
right version, which is an explicit design goal.

These tests guard that wiring: that ``pyproject`` does not reintroduce a second,
hand-synced version literal, and that ``__version__`` is a sane value.
"""
from __future__ import annotations

import re
from pathlib import Path

import exoscale_connector

PYPROJECT = Path(__file__).resolve().parents[2] / "pyproject.toml"


def test_pyproject_version_is_dynamic_not_a_second_literal() -> None:
    text = PYPROJECT.read_text(encoding="utf-8")
    # No static ``version = "..."`` under [project] — that would be a duplicate
    # source of truth kept in lockstep by hand (the bug this setup removes).
    assert re.search(r'(?m)^version\s*=\s*"', text) is None, (
        "pyproject.toml declares a static version; it must stay `dynamic` and "
        "resolve from exoscale_connector.__version__ via [tool.hatch.version]"
    )
    assert re.search(r'(?m)^dynamic\s*=\s*\[[^\]]*"version"', text), (
        "pyproject.toml must mark `version` as dynamic"
    )
    assert 'path = "src/exoscale_connector/__init__.py"' in text, (
        "[tool.hatch.version] must source the version from the package __init__"
    )


def test_version_is_a_sane_pep440_release() -> None:
    assert re.fullmatch(
        r"\d+\.\d+\.\d+([._-]?(a|b|rc|dev|post)\d+)?", exoscale_connector.__version__
    ), f"unexpected __version__ {exoscale_connector.__version__!r}"
