"""Wire-shape recorder for live test runs.

When ``EXOSCALE_RECORD=1`` the live client's session gets a response hook that
appends one sanitized JSON line per API call to ``tests/recorded/``. The
recordings capture the *real* wire shapes the API speaks — the ground truth the
mocked unit suite cannot provide (a mock can use the same wrong key as the code,
so both agree and both are wrong). ``tests/unit/test_recorded_replay.py`` then
replays the recorded GETs offline on every CI run.

Sanitization:

* The ``Authorization`` header is never recorded (nothing reads headers at all).
* Request and response bodies are redacted recursively: any key matching
  ``secret|password|kubeconfig|private-key|token|credential`` has its value
  replaced with ``"[REDACTED]"``.
* Email addresses are scrubbed from every string *value* — on a shared
  tenant they leak into arbitrary content (resource descriptions, labels,
  IAM user lists), so key-based redaction alone cannot catch them.
* Exoscale API key identifiers (``EXO`` + 26 hex chars) are scrubbed the
  same way: the id is the public half of a credential pair and identifies
  real keys on the tenant.

Recordings can still carry tenant-specific identifiers (resource UUIDs, IPs,
zone names) — **review a recording before committing it**.
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any

_SECRET_KEY = re.compile(r"secret|password|kubeconfig|private-key|token|credential", re.I)
_EMAIL = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")
_API_KEY_ID = re.compile(r"\bEXO[0-9a-f]{26}\b")

RECORDINGS_DIR = Path(__file__).resolve().parent.parent / "recorded"


def _sanitize(value: Any) -> Any:
    """Recursively redact secret-bearing keys and scrub emails from values."""
    if isinstance(value, dict):
        return {
            k: "[REDACTED]" if _SECRET_KEY.search(str(k)) else _sanitize(v)
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [_sanitize(item) for item in value]
    if isinstance(value, str):
        value = _EMAIL.sub("[EMAIL-REDACTED]", value)
        return _API_KEY_ID.sub("[KEYID-REDACTED]", value)
    return value


def _parse_json(raw: Any) -> Any:
    if raw is None:
        return None
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8", errors="replace")
    try:
        return json.loads(raw)
    except (ValueError, TypeError):
        return None


def attach_recorder(session: Any, out_path: Path) -> None:
    """Append a sanitized record of every response on *session* to *out_path*."""
    out_path.parent.mkdir(parents=True, exist_ok=True)

    def _record(response: Any, **_: Any) -> Any:
        request = response.request
        entry = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "method": request.method,
            "url": request.url,
            "status": response.status_code,
            "request_body": _sanitize(_parse_json(request.body)),
            "response_body": _sanitize(_parse_json(response.content)),
        }
        with out_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, separators=(",", ":")) + "\n")
        return response

    session.hooks.setdefault("response", []).append(_record)
