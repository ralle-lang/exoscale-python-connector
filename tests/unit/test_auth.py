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
