"""Tests for the generated AI reference bundle (docs/llms.txt).

The sync test is the enforcement point: it fails whenever the committed bundle
no longer matches what the code and asset-type pages would generate, on every
CI run. Regenerate with ``python scripts/generate_llms_txt.py``.
"""
import importlib
import inspect
import pkgutil

from scripts.generate_llms_txt import ASSET_PAGES_DIR, OUTPUT_PATH, generate_bundle

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


def test_bundle_is_in_sync_with_code():
    assert OUTPUT_PATH.exists(), "docs/llms.txt is missing — run scripts/generate_llms_txt.py"
    assert OUTPUT_PATH.read_text(encoding="utf-8") == generate_bundle(), (
        "docs/llms.txt is out of sync with the code/docs — "
        "regenerate with: python scripts/generate_llms_txt.py"
    )


def test_bundle_is_deterministic():
    assert generate_bundle() == generate_bundle()


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
            line for line in page.read_text(encoding="utf-8").splitlines()
            if line.startswith("#")
        )
        assert "##" + first_heading in bundle, f"{page.name} not embedded"
    # The live-verified gotchas are the moat — spot-check one survives verbatim.
    assert "Virtual disk must be ≥ 10 GB" in bundle
