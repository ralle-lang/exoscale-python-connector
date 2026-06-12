"""Keep the minimum-dependency pins honest against the declared floors.

``ci/constraints-min.txt`` pins the runtime dependencies to their declared
minimum versions so the min-deps CI job proves those floors actually work. This
test is the enforcement point — the same self-policing shape as
``ALLOWED_DIVERGENCES`` (model_schema_drift) and ``MODULE_SIBLING_OPERATIONS``
(drift_operations): a pin that drifts from the pyproject floor, a runtime
dependency with no pin, or a stale pin for something that isn't a runtime
dependency all fail the build.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, Tuple

REPO_ROOT = Path(__file__).resolve().parents[2]
PYPROJECT = REPO_ROOT / "pyproject.toml"
CONSTRAINTS = REPO_ROOT / "ci" / "constraints-min.txt"

_NAME = r"[A-Za-z0-9][A-Za-z0-9._-]*"


def _declared_floors() -> Dict[str, str]:
    """Runtime dependency -> declared lower bound, from [project.dependencies].

    Parsed without tomllib so the test runs on the Python 3.9 floor too. The core
    ``dependencies = [...]`` array is unique to [project]; optional-dependencies
    live under their own keys (``dev =``, ``sos =``).
    """
    text = PYPROJECT.read_text(encoding="utf-8")
    match = re.search(r"^dependencies\s*=\s*\[(.*?)\]", text, re.MULTILINE | re.DOTALL)
    assert match, "could not find [project].dependencies in pyproject.toml"
    floors: Dict[str, str] = {}
    for raw in re.findall(r'"([^"]+)"', match.group(1)):
        name = re.match(_NAME, raw)
        lower = re.search(r">=\s*([0-9][0-9.]*)", raw)
        assert name and lower, f"runtime dependency {raw!r} has no `>=` floor to pin against"
        floors[_canonical(name.group(0))] = lower.group(1)
    return floors


def _constraint_pins() -> Dict[str, str]:
    """Constraint name -> pinned version, from the `==` lines of the constraints file."""
    pins: Dict[str, str] = {}
    for line in CONSTRAINTS.read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        match = re.fullmatch(rf"({_NAME})==([0-9][0-9.]*)", line)
        assert match, f"constraints-min.txt line is not a simple `name==version` pin: {line!r}"
        pins[_canonical(match.group(1))] = match.group(2)
    return pins


def _canonical(name: str) -> str:
    return name.lower().replace("_", "-")


def _minor(version: str) -> Tuple[int, int]:
    parts = [int(p) for p in version.split(".")[:2]]
    while len(parts) < 2:
        parts.append(0)
    return parts[0], parts[1]


def test_every_runtime_dependency_has_a_minimum_pin():
    """No missing pins and no stale pins: the pin set matches the floor set exactly."""
    floors = _declared_floors()
    pins = _constraint_pins()
    assert set(pins) == set(floors), (
        "ci/constraints-min.txt is out of sync with the pyproject runtime "
        f"dependencies. floors={sorted(floors)} pinned={sorted(pins)} — add a pin "
        "for a new dependency, or remove a stale one."
    )


def test_each_pin_matches_its_declared_floor():
    """Each pin's major.minor must equal the declared `>=` floor's major.minor."""
    floors = _declared_floors()
    pins = _constraint_pins()
    for name, floor in floors.items():
        assert _minor(pins[name]) == _minor(floor), (
            f"{name}: constraints-min.txt pins =={pins[name]} but pyproject floor is "
            f">={floor} — bump the pin to the new floor (they must track each other)."
        )
