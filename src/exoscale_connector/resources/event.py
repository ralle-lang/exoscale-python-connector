"""Audit Event resource client (read-only).

Wraps ``GET /event``, the account audit log: one entry per APIv2 request, with
the caller identity (IAM user / role / API key), the HTTP method+path, the
zone, and the outcome. Handy as a "what changed / who did it" check after an
automated provisioning run.

The endpoint returns a bare JSON array (not the usual ``{"events": [...]}``
envelope); the client normalises that so :meth:`list` behaves like every other
resource client.

API reference: https://openapi-v2.exoscale.com/group/endpoint-audit
"""

from __future__ import annotations

import builtins

from ..models import ExoscaleModel, Reference
from ._base import ResourceClient


class Event(ExoscaleModel):
    """A single audit-log entry describing one APIv2 request."""

    timestamp: str | None = None
    # HTTP request line details.
    handler: str | None = None
    uri: str | None = None
    status: int | None = None
    elapsed_ms: int | None = None
    request_id: str | None = None
    source_ip: str | None = None
    message: str | None = None
    zone: str | None = None
    # Caller identity (whichever applies to the request).
    iam_user: Reference | None = None
    iam_role: Reference | None = None
    iam_api_key: Reference | None = None


class EventClient(ResourceClient[Event]):
    """Read the account audit event stream (``GET /event``).

    Read-only: only :meth:`list` is meaningful. Optionally bound the window
    with ``from_``/``to`` (ISO-8601 timestamps); omitted, the API returns its
    default recent window.
    """

    collection_path = "event"
    model = Event
    # GET /event is a bare array; ExoscaleClient wraps non-object bodies as
    # {"data": [...]}, so the array lives under "data".
    list_key = "data"

    def list(  # type: ignore[override]
        self,
        *,
        from_: str | None = None,
        to: str | None = None,
        zone: str | None = None,
    ) -> builtins.list[Event]:
        """Return audit events, newest window first.

        ``from_`` and ``to`` are ISO-8601 timestamps mapped to the API's
        ``from``/``to`` query parameters (``from`` is a Python keyword, hence
        the trailing underscore).
        """
        params = {}
        if from_ is not None:
            params["from"] = from_
        if to is not None:
            params["to"] = to
        payload = self.client.get(
            self.collection_path, zone=self._zone(zone), params=params or None
        )
        items = payload.get(self.list_key) or []
        return [self.model.model_validate(item) for item in items if isinstance(item, dict)]
