"""Unit tests for the live-run wire recorder (sanitization + hook plumbing)."""
from __future__ import annotations

import json

import responses
from tests.integration._recorder import _sanitize, attach_recorder

from exoscale_connector.client import ExoscaleClient


def test_sanitize_redacts_secretish_keys_recursively() -> None:
    body = {
        "name": "ok",
        "secret": "live-credential",
        "user": {"password": "hunter2", "username": "kept"},
        "items": [{"api-token": "abc", "id": "kept"}],
    }
    clean = _sanitize(body)
    assert clean["secret"] == "[REDACTED]"
    assert clean["user"]["password"] == "[REDACTED]"
    assert clean["items"][0]["api-token"] == "[REDACTED]"
    assert clean["name"] == "ok" and clean["user"]["username"] == "kept"
    assert clean["items"][0]["id"] == "kept"


def test_sanitize_scrubs_emails_from_string_values() -> None:
    # Emails leak into arbitrary content on a shared tenant (descriptions,
    # labels, IAM user lists) where no secret-looking key flags them.
    body = {
        "description": "owner: jane.doe@example.com, escalate to ops@corp.example.org",
        "labels": {"contact": "john@example.com"},
        "items": [{"email": "kept-key@example.com"}],
    }
    clean = _sanitize(body)
    assert clean["description"] == "owner: [EMAIL-REDACTED], escalate to [EMAIL-REDACTED]"
    assert clean["labels"]["contact"] == "[EMAIL-REDACTED]"
    assert clean["items"][0]["email"] == "[EMAIL-REDACTED]"


@responses.activate
def test_recorder_writes_sanitized_jsonl(client, base_url, tmp_path) -> None:
    responses.add(
        responses.GET,
        f"{base_url}/api-key/EXOabc",
        json={"key": "EXOabc", "secret": "leakme"},
        status=200,
    )
    out = tmp_path / "rec.jsonl"
    attach_recorder(client._session, out)
    client.get("api-key/EXOabc")

    entry = json.loads(out.read_text().splitlines()[0])
    assert entry["method"] == "GET"
    assert entry["status"] == 200
    assert entry["response_body"]["secret"] == "[REDACTED]"
    assert "Authorization" not in out.read_text()
    assert isinstance(client, ExoscaleClient)
