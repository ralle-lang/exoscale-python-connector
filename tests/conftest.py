"""Shared pytest fixtures for unit tests.

Unit tests never touch the network: a :class:`ClientConfig` with dummy
credentials and zero retry backoff drives an :class:`ExoscaleClient` whose HTTP
calls are intercepted by the ``responses`` library.
"""
from __future__ import annotations

import pytest

from exoscale_connector.client import ExoscaleClient
from exoscale_connector.config import ClientConfig

TEST_ZONE = "de-fra-1"
BASE_URL = f"https://api-{TEST_ZONE}.exoscale.com/v2"


@pytest.fixture
def config() -> ClientConfig:
    """A config with fake credentials and no backoff (fast retries in tests)."""
    return ClientConfig(
        api_key="EXOtestkey",
        api_secret="testsecret",
        zone=TEST_ZONE,
        retry_backoff=0.0,
    )


@pytest.fixture
def client(config: ClientConfig) -> ExoscaleClient:
    return ExoscaleClient(config)


@pytest.fixture
def base_url() -> str:
    return BASE_URL
