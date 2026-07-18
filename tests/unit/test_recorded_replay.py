"""Replay recorded live wire shapes offline.

Every ``tests/recorded/*.jsonl`` file (produced by a live run with
``EXOSCALE_RECORD=1``, see ``tests/integration/_recorder.py``) is replayed
against the request layer: each recorded GET is registered as a mocked
response at its original URL and re-issued through a real ``ExoscaleClient``.
This proves the connector still accepts the API's *actual* wire shapes —
the failure mode a hand-written mock can't catch.

With no recordings present the suite is skipped, not failed.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import responses

from exoscale_connector.client import ExoscaleClient
from exoscale_connector.config import ClientConfig

RECORDINGS_DIR = Path(__file__).resolve().parent.parent / "recorded"


def _recorded_gets():
    params = []
    if not RECORDINGS_DIR.is_dir():
        return params
    for path in sorted(RECORDINGS_DIR.glob("*.jsonl")):
        for line_no, line in enumerate(path.read_text().splitlines(), start=1):
            if not line.strip():
                continue
            entry = json.loads(line)
            if (
                entry.get("method") == "GET"
                and entry.get("status") == 200
                and isinstance(entry.get("response_body"), dict)
                and "/v2/" in (entry.get("url") or "")
            ):
                params.append(
                    pytest.param(entry, id=f"{path.stem}:{line_no}:{entry['url'].split('/v2/')[1]}")
                )
    return params


_RECORDED = _recorded_gets()


@pytest.mark.skipif(not _RECORDED, reason="no recorded wire fixtures (tests/recorded/)")
@pytest.mark.parametrize("entry", _RECORDED)
@responses.activate
def test_recorded_get_replays_through_client(entry: dict) -> None:
    base, _, path = entry["url"].partition("/v2/")
    responses.add(responses.GET, entry["url"], json=entry["response_body"], status=200)
    client = ExoscaleClient(
        ClientConfig(api_key="EXOreplay", api_secret="replay", endpoint=f"{base}/v2")
    )
    parsed = client.get(path)
    assert parsed == entry["response_body"]
