"""Exoscale APIv2 request signing.

Exoscale's APIv2 authenticates each request with an ``EXO2-HMAC-SHA256`` signature
built from the request method, path, selected query-string values and an expiry
timestamp. This module vendors a zero-dependency (beyond ``requests``) implementation
so the connector stays self-contained and copy-pastable into other projects.

The signing scheme is documented at
https://openapi-v2.exoscale.com/topic/topic-api-request-signature
"""

from __future__ import annotations

import hashlib
import hmac
import time
from base64 import standard_b64encode
from urllib.parse import parse_qs, urlparse

from requests.auth import AuthBase
from requests.models import PreparedRequest


class ExoscaleV2Auth(AuthBase):
    """``requests`` auth handler that signs requests for the Exoscale APIv2.

    Attach an instance to a ``requests.Session`` (``session.auth = ExoscaleV2Auth(...)``)
    and every request is signed automatically just before it is sent.
    """

    def __init__(self, key: str, secret: str, *, expiration_seconds: int = 600) -> None:
        if not key or not secret:
            raise ValueError("Exoscale API key and secret are both required")
        self.key = key
        self.secret = secret.encode("utf-8")
        # Signatures embed an absolute expiry; keep the window short to limit replay risk.
        self.expiration_seconds = expiration_seconds

    def __call__(self, request: PreparedRequest) -> PreparedRequest:
        expiration_ts = int(time.time() + self.expiration_seconds)
        self._sign_request(request, expiration_ts)
        return request

    def _sign_request(self, request: PreparedRequest, expiration_ts: int) -> None:
        """Compute the signature and write it into the ``Authorization`` header.

        The signed message is the newline-joined concatenation of:
        ``"<METHOD> <path>"``, the request body, the selected query-arg values,
        an (empty) headers segment, and the expiry timestamp. Query args that are
        signed are advertised back to the server via ``signed-query-args``.
        """
        auth_header = f"EXO2-HMAC-SHA256 credential={self.key}"
        msg_parts: list[bytes] = []

        parsed = urlparse(request.url or "")
        msg_parts.append(f"{request.method} {parsed.path}".encode("utf-8"))

        body = request.body or b""
        if isinstance(body, str):
            body = body.encode("utf-8")
        msg_parts.append(body)

        # Only single-valued query params are signed; multi-valued ones are skipped
        # to keep the canonicalisation unambiguous.
        params = parse_qs(parsed.query)
        signed_params = sorted(p for p in params if len(params[p]) == 1)
        msg_parts.append("".join(params[p][0] for p in signed_params).encode("utf-8"))
        if signed_params:
            auth_header += f",signed-query-args={';'.join(signed_params)}"

        # No request headers are part of the signature in this connector.
        msg_parts.append(b"")
        msg_parts.append(str(expiration_ts).encode("utf-8"))
        auth_header += f",expires={expiration_ts}"

        signature = hmac.new(self.secret, b"\n".join(msg_parts), hashlib.sha256).digest()
        auth_header += f",signature={standard_b64encode(signature).decode('utf-8')}"

        request.headers["Authorization"] = auth_header
