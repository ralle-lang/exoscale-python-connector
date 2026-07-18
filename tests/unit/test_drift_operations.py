"""Self-enforcing tests for the module -> APIv2 operations map.

The mapping in ``scripts/drift_operations.py`` is how the upstream-drift workflow
turns a spec change into "these connector modules are affected". These tests make
the mapping honest the same way ``test_llms_txt`` keeps the bundle honest: they
fail if the code calls an endpoint the mapping can't attribute, or if the mapping
carries a sibling no module actually uses.
"""

from __future__ import annotations

from scripts.drift_operations import (
    MODULE_SIBLING_OPERATIONS,
    affected_modules,
    changed_spec_paths,
    discovered_operations,
    template_covers,
    undeclared_siblings,
)


def test_every_called_endpoint_is_attributed_to_a_module():
    """Fails if any module calls a sibling endpoint missing from the mapping.

    This is the enforcement point: add a client call to an endpoint outside the
    module's own collection path without declaring it, and this test goes red.
    """
    missing = undeclared_siblings()
    assert missing == {}, (
        "Undeclared sibling operations — add them to "
        f"MODULE_SIBLING_OPERATIONS in scripts/drift_operations.py: {missing}"
    )


def test_no_stale_declared_siblings():
    """Every declared sibling must attribute at least one real client call."""
    discovered = discovered_operations()
    for module, siblings in MODULE_SIBLING_OPERATIONS.items():
        endpoints = discovered.get(module, [])
        for sibling in siblings:
            assert any(template_covers(sibling, ep) for ep in endpoints), (
                f"{module}: declared sibling {sibling!r} matches no endpoint the "
                "code calls — remove it from MODULE_SIBLING_OPERATIONS"
            )


def test_template_covers_respects_segment_boundaries():
    # Collection path must not swallow a same-prefix sibling.
    assert template_covers("sks-cluster", "sks-cluster/{}/nodepool")
    assert not template_covers("sks-cluster", "sks-cluster-version")
    # {} matches exactly one segment; trailing * matches a segment prefix.
    assert template_covers("private-network/{}:attach", "private-network/{}:attach")
    assert template_covers("dbaas-*", "dbaas-postgres/{}")
    assert not template_covers("dbaas-*", "instance/{}")


def test_affected_modules_maps_changed_paths():
    base = {
        "paths": {
            "/sks-cluster/{id}": {"v": 1},
            "/private-network/{id}:attach": {"v": 1},
            "/orphan-endpoint/{id}": {"v": 1},
        }
    }
    revision = {
        "paths": {
            "/sks-cluster/{id}": {"v": 2},  # changed
            # private-network attach removed
            "/sks-cluster-version": {"v": 1},  # added (sibling endpoint)
            "/orphan-endpoint/{id}": {"v": 2},  # changed, no module
        }
    }
    changed = changed_spec_paths(base, revision)
    by_module, unmatched = affected_modules(changed)

    sks = "src/exoscale_connector/resources/sks.py"
    pn = "src/exoscale_connector/resources/private_network.py"
    assert sks in by_module
    sks_paths = {p for p, _ in by_module[sks]}
    assert "sks-cluster/{}" in sks_paths  # via collection-path prefix
    assert "sks-cluster-version" in sks_paths  # via declared sibling
    assert pn in by_module  # the removed attach path still attributes
    # The endpoint no module uses is surfaced, not silently dropped.
    assert ("orphan-endpoint/{}", "changed") in unmatched


def test_changed_spec_paths_classifies_add_remove_change():
    base = {"paths": {"/a": {"x": 1}, "/b": {"x": 1}}}
    revision = {"paths": {"/a": {"x": 2}, "/c": {"x": 1}}}
    changed = changed_spec_paths(base, revision)
    assert changed == {"a": "changed", "b": "removed", "c": "added"}
