"""Unit tests for ClientConfig credential hygiene and TLS/timeout settings."""

from __future__ import annotations

import warnings

import pytest

from exoscale_connector.config import ClientConfig


def test_repr_does_not_leak_credentials() -> None:
    config = ClientConfig(api_key="EXOleakkey", api_secret="leaksecret", zone="de-fra-1")
    rendered = repr(config)
    assert "EXOleakkey" not in rendered
    assert "leaksecret" not in rendered
    # Non-sensitive fields stay visible for debuggability.
    assert "de-fra-1" in rendered


def test_disabling_tls_verification_warns() -> None:
    with pytest.warns(UserWarning, match="TLS certificate verification is DISABLED"):
        ClientConfig(api_key="k", api_secret="s", verify_tls=False)


def test_default_config_does_not_warn() -> None:
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        ClientConfig(api_key="k", api_secret="s")


def test_operation_timeout_default_is_longer_than_request_timeout() -> None:
    config = ClientConfig(api_key="k", api_secret="s")
    assert config.operation_timeout == 600.0
    assert config.operation_timeout > config.timeout
