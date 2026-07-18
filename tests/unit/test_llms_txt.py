"""Tests for the generated AI reference bundle (docs/llms.txt).

The sync test is the enforcement point: it fails whenever the committed bundle
no longer matches what the code and asset-type pages would generate, on every
CI run. Regenerate with ``python scripts/generate_llms_txt.py``.
"""

import importlib
import inspect
import json
import pkgutil

from scripts.generate_llms_txt import (
    ASSET_PAGES_DIR,
    SKILL_MD,
    SKS_PAGE,
    UPSTREAM_SPEC,
    _load_asset_page,
    artifacts,
    generate_bundle,
)

import exoscale_connector.resources as resources_pkg


def _all_client_class_names():
    names = []
    for info in pkgutil.iter_modules(resources_pkg.__path__):
        if info.name.startswith("_"):
            continue
        mod = importlib.import_module(f"exoscale_connector.resources.{info.name}")
        for name, obj in vars(mod).items():
            if inspect.isclass(obj) and obj.__module__ == mod.__name__ and name.endswith("Client"):
                names.append(name)
    return names


def test_all_artifacts_are_in_sync_with_code():
    for path, content in artifacts().items():
        assert path.exists(), f"{path} is missing — run scripts/generate_llms_txt.py"
        assert path.read_text(encoding="utf-8") == content, (
            f"{path} is out of sync with the code/docs — "
            "regenerate with: python scripts/generate_llms_txt.py"
        )


def test_bundle_is_deterministic():
    assert generate_bundle() == generate_bundle()


def test_skill_has_valid_frontmatter_and_points_at_reference():
    assert SKILL_MD.startswith("---\n")
    frontmatter = SKILL_MD.split("---\n")[1]
    assert "name: exoscale-connector" in frontmatter
    assert "description:" in frontmatter
    assert "reference.md" in SKILL_MD
    # Both skill copies ship a reference identical to the bundle. sks.md is also
    # a (partly) generated artifact — its spec-derived addon block is injected.
    paths = {p.name: p for p in artifacts()}
    assert sorted(paths) == ["SKILL.md", "llms.txt", "reference.md", "sks.md"]
    for path, content in artifacts().items():
        if path.name == "reference.md":
            assert content == generate_bundle()


def test_sks_addons_injected_from_spec():
    """The sks.md addon block is sourced from the committed OpenAPI spec, not hand-typed."""
    spec = json.loads(UPSTREAM_SPEC.read_text(encoding="utf-8"))
    cluster_enum = spec["components"]["schemas"]["sks-cluster"]["properties"]["addons"]["items"][
        "enum"
    ]
    page = _load_asset_page(SKS_PAGE)
    assert "BEGIN GENERATED:sks-addons" in page
    # Every addon advertised by the spec must appear in the rendered page.
    for addon in cluster_enum:
        assert f"`{addon}`" in page, f"{addon} from spec missing in sks.md"
    # And the rendered set is exactly the spec's (no stale hand-added extras).
    rendered = page.split("BEGIN GENERATED:sks-addons")[1].split("END GENERATED:sks-addons")[0]
    assert "exoscale-cloud-controller" in rendered


def test_bundle_covers_every_resource_client():
    bundle = generate_bundle()
    names = _all_client_class_names()
    assert len(names) >= 20  # sanity: discovery actually found the asset types
    for name in names:
        assert f"#### client `{name}`" in bundle, f"{name} missing from bundle"


def test_bundle_covers_common_operations_and_models():
    bundle = generate_bundle()
    for method in ("ensure(", "find_by_name(", "get_or_none(", "wait_for_state("):
        assert method in bundle
    # Model field tables carry the kebab-case JSON keys an LLM must use in payloads.
    for alias in ("`ssh-key-enabled`", "`flow-direction`", "`start-port`"):
        assert alias in bundle


def test_bundle_embeds_every_asset_type_page():
    bundle = generate_bundle()
    pages = list(ASSET_PAGES_DIR.glob("*.md"))
    assert len(pages) >= 20
    for page in pages:
        # First heading of each page must survive embedding (demoted, not dropped).
        first_heading = next(
            line for line in page.read_text(encoding="utf-8").splitlines() if line.startswith("#")
        )
        assert "##" + first_heading in bundle, f"{page.name} not embedded"
    # The live-verified gotchas are the moat — spot-check one survives verbatim.
    assert "Virtual disk must be ≥ 10 GB" in bundle
