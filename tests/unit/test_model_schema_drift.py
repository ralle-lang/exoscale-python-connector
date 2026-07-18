"""Self-enforcing tests: pydantic models vs the committed OpenAPI schema.

These keep the typed surface honest against the *published contract* the same way
``test_drift_operations`` keeps the module map honest and ``test_llms_txt`` keeps the
AI bundle honest. They diff every resource model's fields against
``.github/upstream/openapi-v2.json`` and fail on drift the live tests can sail past
(a model wired to a wrong/renamed wire key still round-trips, because
``extra="allow"`` absorbs the real key and a lifecycle test rarely asserts on every
field). Intentional, live-verified divergences live in
``ALLOWED_DIVERGENCES`` with a reason; the allowlist is itself policed for staleness.
"""

from __future__ import annotations

from scripts.model_schema_drift import (
    UPSTREAM_SPEC,
    all_drift,
    invalid_mapping_entries,
    load_schemas,
    resolve_schema,
    stale_allowlist_entries,
    unresolved_models,
)


def _schemas():
    return load_schemas(UPSTREAM_SPEC)


def test_every_resource_model_resolves_to_a_schema():
    """A new asset type must map to a schema (collection_path / alias) or be exempt."""
    unresolved = unresolved_models(_schemas())
    assert unresolved == [], (
        "Models with no schema mapping — add a SCHEMA_ALIASES or EXEMPT_MODELS entry "
        f"in scripts/model_schema_drift.py: {unresolved}"
    )


def test_mapping_entries_reference_real_models_and_schemas():
    """SCHEMA_ALIASES / EXEMPT_MODELS must not point at a vanished model or schema."""
    invalid = invalid_mapping_entries(_schemas())
    assert invalid == {}, f"Invalid model->schema mapping entries: {invalid}"


def test_no_model_field_drift_against_the_spec():
    """The enforcement point: every model matches its schema or an allowlisted delta.

    Add/rename/remove/retype a model field so it no longer matches the OpenAPI
    snapshot (and isn't an intentional, allowlisted divergence) and this goes red.
    """
    failing = {
        d.model_name: {
            "model_only": d.model_only,
            "type_mismatch": d.type_mismatch,
            "missing_required": d.missing_required,
        }
        for d in all_drift(_schemas())
        if d.has_failures
    }
    assert failing == {}, (
        "Model/spec field drift. Reconcile the model with the spec, or record an "
        "intentional divergence in ALLOWED_DIVERGENCES (with a reason) in "
        f"scripts/model_schema_drift.py: {failing}"
    )


def test_allowlist_has_no_stale_entries():
    """Every ALLOWED_DIVERGENCES entry must suppress a real mismatch this run."""
    stale = stale_allowlist_entries(_schemas())
    assert stale == {}, (
        "Stale ALLOWED_DIVERGENCES entries — the divergence is gone, remove them "
        f"from scripts/model_schema_drift.py: {stale}"
    )


def test_resolve_schema_follows_ref_and_allof():
    schemas = {
        "base": {"type": "object", "properties": {"id": {"type": "string"}}, "required": ["id"]},
        "thing": {
            "allOf": [
                {"$ref": "#/components/schemas/base"},
                {"type": "object", "properties": {"name": {"type": "string"}}},
            ]
        },
        "wrapped": {"$ref": "#/components/schemas/thing"},
    }
    props, required = resolve_schema(schemas["wrapped"], schemas)
    assert props == {"id": "string", "name": "string"}
    assert required == {"id"}


def test_resolve_schema_dereferences_enum_string_to_string():
    """A $ref to an enum-string schema is a string family, not an object."""
    schemas = {
        "state": {"type": "string", "enum": ["running", "stopped"]},
        "box": {"type": "object", "properties": {"state": {"$ref": "#/components/schemas/state"}}},
    }
    props, _ = resolve_schema(schemas["box"], schemas)
    assert props == {"state": "string"}
