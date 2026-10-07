"""Unit tests for ClientConfig credential hygiene and TLS/timeout settings."""

from __future__ import annotations

import warnings

import pytest

from exoscale_connector.config import ClientConfig
from exoscale_connector.errors import ConfigError


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


@pytest.fixture
def creds_env(monkeypatch):
    monkeypatch.setenv("EXOSCALE_API_KEY", "EXOtestkey")
    monkeypatch.setenv("EXOSCALE_API_SECRET", "testsecret")
    monkeypatch.delenv("EXOSCALE_VERIFY_TLS", raising=False)
    return monkeypatch


@pytest.mark.parametrize("raw", [None, "", "   ", "true", "1", "YES", "on"])
def test_verify_tls_stays_on_for_unset_blank_or_truthy(creds_env, raw) -> None:
    if raw is not None:
        creds_env.setenv("EXOSCALE_VERIFY_TLS", raw)
    assert ClientConfig.from_env().verify_tls is True


@pytest.mark.parametrize("raw", ["false", "0", "No", "off"])
def test_verify_tls_can_be_disabled_explicitly(creds_env, raw) -> None:
    creds_env.setenv("EXOSCALE_VERIFY_TLS", raw)
    with pytest.warns(UserWarning):
        assert ClientConfig.from_env().verify_tls is False


def test_verify_tls_rejects_unrecognised_value(creds_env) -> None:
    creds_env.setenv("EXOSCALE_VERIFY_TLS", "maybe")
    with pytest.raises(ConfigError, match="EXOSCALE_VERIFY_TLS"):
        ClientConfig.from_env()
