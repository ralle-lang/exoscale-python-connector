"""The packaged ``__version__`` must match the distribution version.

``pyproject.toml`` drives what PyPI publishes; ``exoscale_connector.__version__``
drives the CLI ``--version`` output and the "Package version" line embedded in
the generated AI bundle. They are kept in lockstep by hand at release time —
this test fails CI on a mismatch instead of shipping a wheel whose embedded
version disagrees with the published distribution.
"""
from __future__ import annotations

import re
from pathlib import Path

import exoscale_connector

PYPROJECT = Path(__file__).resolve().parents[2] / "pyproject.toml"


def test_package_version_matches_pyproject() -> None:
    text = PYPROJECT.read_text(encoding="utf-8")
    match = re.search(r'(?m)^version\s*=\s*"([^"]+)"', text)
    assert match, "no [project] version found in pyproject.toml"
    assert match.group(1) == exoscale_connector.__version__, (
        f"pyproject version {match.group(1)!r} != "
        f"__version__ {exoscale_connector.__version__!r}"
    )
