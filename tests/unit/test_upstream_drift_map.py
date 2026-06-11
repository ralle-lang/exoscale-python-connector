"""Tests for the upstream-drift path → module mapping script."""

from scripts.upstream_drift_map import REPO_ROOT, main, mapping_rows


def test_mapping_covers_every_apiv2_resource_client():
    rows = mapping_rows()
    assert len(rows) >= 20  # sanity: discovery actually found the asset types
    clients = {client for _, client, _, _ in rows}
    assert "TemplateClient" in clients
    assert "BucketClient" not in clients  # SOS is outside the APIv2 spec


def test_every_mapped_module_and_doc_page_exists():
    for path, client, module, doc in mapping_rows():
        assert path.startswith("/") and len(path) > 1
        assert (REPO_ROOT / module).is_file(), f"{module} missing for {client}"
        assert (REPO_ROOT / doc).is_file(), f"{doc} missing for {client}"


def test_mapping_is_deterministic():
    assert mapping_rows() == mapping_rows()


def test_main_prints_markdown_table(capsys):
    assert main() == 0
    out = capsys.readouterr().out
    assert "| Spec path prefix | Client | Module | Doc page |" in out
    assert "| `/template` | `TemplateClient` |" in out
    assert "Object Storage (SOS)" in out


def test_snapshot_files_are_seeded():
    upstream = REPO_ROOT / ".github" / "upstream"
    spec = upstream / "openapi-v2.json"
    version = upstream / "python-exoscale-version.txt"
    assert spec.is_file() and spec.stat().st_size > 100_000
    assert version.is_file() and version.read_text().strip()
