"""Unit tests for the EXO2-HMAC-SHA256 request signer."""

from __future__ import annotations

import requests

from exoscale_connector.auth import ExoscaleV2Auth


def _sign(url: str, method: str = "GET", body=None) -> str:
    """Prepare and sign a request, returning its Authorization header."""
    req = requests.Request(method, url, data=body)
    prepared = req.prepare()
    ExoscaleV2Auth("EXOkey", "secret")(prepared)
    return prepared.headers["Authorization"]


def test_authorization_header_structure() -> None:
    header = _sign("https://api-de-fra-1.exoscale.com/v2/security-group")
    assert header.startswith("EXO2-HMAC-SHA256 credential=EXOkey")
    assert ",expires=" in header
    assert ",signature=" in header


def test_query_args_are_advertised_when_present() -> None:
    header = _sign("https://api-de-fra-1.exoscale.com/v2/instance?zone=de-fra-1&visibility=public")
    # Both single-valued params must be listed, sorted, semicolon-joined.
    assert "signed-query-args=visibility;zone" in header


def test_no_signed_query_args_segment_without_query() -> None:
    header = _sign("https://api-de-fra-1.exoscale.com/v2/instance")
    assert "signed-query-args" not in header


def test_missing_credentials_rejected() -> None:
    import pytest

    with pytest.raises(ValueError):
        ExoscaleV2Auth("", "secret")


# Golden vectors: each signature was computed once, independently of the
# implementation, as base64(HMAC-SHA256(b"secret", <message>)) over the literal
# wire-format message in the comment. A change to the canonical message
# (line order, separators, path vs URL, query-value order, body encoding)
# breaks these instead of surfacing as an opaque 403 against the live API.
_EXPIRES = 1700000000


def _sign_at(method: str, url: str, body=None) -> str:
    prepared = requests.Request(method, url, data=body).prepare()
    ExoscaleV2Auth("EXOkey", "secret")._sign_request(prepared, _EXPIRES)
    return prepared.headers["Authorization"]


def test_golden_signature_get_with_query_args() -> None:
    # b"GET /v2/instance\n\npublicde-fra-1\n\n1700000000"
    assert _sign_at(
        "GET", "https://api-de-fra-1.exoscale.com/v2/instance?zone=de-fra-1&visibility=public"
    ) == (
        "EXO2-HMAC-SHA256 credential=EXOkey,signed-query-args=visibility;zone,"
        "expires=1700000000,signature=cPwqEt63iUH70ZqT47vBoLsuGJucS88ln82VSSRjFuc="
    )


def test_golden_signature_post_with_utf8_body() -> None:
    # b'POST /v2/security-group\n{"name": "web-\xc3\xa9"}\n\n\n1700000000'
    body = '{"name": "web-é"}'.encode()
    assert _sign_at("POST", "https://api-de-fra-1.exoscale.com/v2/security-group", body) == (
        "EXO2-HMAC-SHA256 credential=EXOkey,"
        "expires=1700000000,signature=nTHJuLN5AavXsiFzm1WVvwk+wy4bABQtA0Zd2d8veyk="
    )


def test_golden_signature_skips_multi_valued_query_args() -> None:
    # Only the single-valued "b" is signed: b"GET /v2/event\n\n3\n\n1700000000"
    assert _sign_at("GET", "https://api-de-fra-1.exoscale.com/v2/event?a=1&a=2&b=3") == (
        "EXO2-HMAC-SHA256 credential=EXOkey,signed-query-args=b,"
        "expires=1700000000,signature=BXymwnQklXI1fb4zYu9w3YzNVirsSWtHfvb0nM9vOUk="
    )


def test_call_expires_after_expiration_window(monkeypatch) -> None:
    monkeypatch.setattr("exoscale_connector.auth.time.time", lambda: 1000.0)
    prepared = requests.Request("GET", "https://api-de-fra-1.exoscale.com/v2/zone").prepare()
    ExoscaleV2Auth("EXOkey", "secret", expiration_seconds=300)(prepared)
    assert ",expires=1300," in prepared.headers["Authorization"]
