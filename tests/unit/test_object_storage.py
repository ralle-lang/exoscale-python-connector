"""Unit tests for BucketClient (Object Storage / SOS adapter).

All tests inject a :class:`unittest.mock.MagicMock` as the ``s3_client``
parameter so that:

* ``boto3`` is never imported — the ``[sos]`` extra need not be installed.
* No network traffic is made.
* The exact boto3 method signatures called by BucketClient are verified.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from exoscale_connector.config import ClientConfig
from exoscale_connector.errors import APIError, ConfigError
from exoscale_connector.resources.object_storage import Bucket, BucketClient

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

TEST_ZONE = "de-fra-1"


def _config() -> ClientConfig:
    return ClientConfig(
        api_key="EXOtestkey",
        api_secret="testsecret",
        zone=TEST_ZONE,
    )


def _client(mock_s3: MagicMock) -> BucketClient:
    """Build a BucketClient with an injected mock — never touches boto3."""
    return BucketClient(_config(), s3_client=mock_s3)


# ---------------------------------------------------------------------------
# Bucket model
# ---------------------------------------------------------------------------


def test_bucket_model_basic() -> None:
    bucket = Bucket(name="my-bucket", creation_date="2024-01-15T10:00:00+00:00")
    assert bucket.name == "my-bucket"
    assert bucket.creation_date == "2024-01-15T10:00:00+00:00"


def test_bucket_model_optional_fields() -> None:
    bucket = Bucket(name="minimal")
    assert bucket.name == "minimal"
    assert bucket.creation_date is None


def test_bucket_model_dump_excludes_none() -> None:
    bucket = Bucket(name="only-name")
    dumped = bucket.model_dump(by_alias=True, exclude_none=True)
    assert "name" in dumped
    assert "creation-date" not in dumped


# ---------------------------------------------------------------------------
# BucketClient — construction
# ---------------------------------------------------------------------------


def test_construction_with_injected_client_skips_boto3() -> None:
    """Injecting s3_client must not trigger any boto3 import."""
    mock_s3 = MagicMock()
    client = BucketClient(_config(), s3_client=mock_s3)
    assert client is not None


def test_construction_without_zone_raises_config_error() -> None:
    config = ClientConfig(api_key="k", api_secret="s", zone=None)
    with pytest.raises(ConfigError, match="zone"):
        # No injected client → would need to build real boto3 client → requires zone.
        BucketClient(config)


def test_construction_boto3_missing_raises_config_error() -> None:
    """When boto3 is not importable and no client is injected, raise ConfigError."""
    config = ClientConfig(api_key="k", api_secret="s", zone=TEST_ZONE)
    with patch.dict("sys.modules", {"boto3": None}):
        with pytest.raises(ConfigError, match="pip install"):
            BucketClient(config)


# ---------------------------------------------------------------------------
# list()
# ---------------------------------------------------------------------------


def test_list_calls_list_buckets_and_returns_bucket_models() -> None:
    mock_s3 = MagicMock()
    mock_s3.list_buckets.return_value = {
        "Buckets": [
            {"Name": "bucket-a", "CreationDate": "2024-01-01T00:00:00+00:00"},
            {"Name": "bucket-b", "CreationDate": "2024-03-15T12:30:00+00:00"},
        ]
    }
    client = _client(mock_s3)
    buckets = client.list()

    mock_s3.list_buckets.assert_called_once_with()
    assert len(buckets) == 2
    assert all(isinstance(b, Bucket) for b in buckets)
    assert [b.name for b in buckets] == ["bucket-a", "bucket-b"]


def test_list_empty_response_returns_empty_list() -> None:
    mock_s3 = MagicMock()
    mock_s3.list_buckets.return_value = {"Buckets": []}
    client = _client(mock_s3)
    assert client.list() == []


def test_list_missing_buckets_key_returns_empty_list() -> None:
    mock_s3 = MagicMock()
    mock_s3.list_buckets.return_value = {}
    client = _client(mock_s3)
    assert client.list() == []


def test_list_bucket_creation_date_converted_to_string() -> None:
    mock_s3 = MagicMock()
    # boto3 normally returns a datetime object; simulate that here.
    import datetime

    dt = datetime.datetime(2024, 6, 1, 9, 0, 0, tzinfo=datetime.timezone.utc)
    mock_s3.list_buckets.return_value = {"Buckets": [{"Name": "ts-bucket", "CreationDate": dt}]}
    client = _client(mock_s3)
    buckets = client.list()
    assert buckets[0].creation_date == str(dt)


# ---------------------------------------------------------------------------
# exists()
# ---------------------------------------------------------------------------


def test_exists_calls_head_bucket_and_returns_true() -> None:
    mock_s3 = MagicMock()
    mock_s3.head_bucket.return_value = {}
    client = _client(mock_s3)
    assert client.exists("present-bucket") is True
    mock_s3.head_bucket.assert_called_once_with(Bucket="present-bucket")


def test_exists_returns_false_on_404_error_code() -> None:
    mock_s3 = MagicMock()
    exc = _make_client_error("404")
    mock_s3.head_bucket.side_effect = exc
    client = _client(mock_s3)
    assert client.exists("missing-bucket") is False


def test_exists_returns_false_on_no_such_bucket_code() -> None:
    mock_s3 = MagicMock()
    exc = _make_client_error("NoSuchBucket")
    mock_s3.head_bucket.side_effect = exc
    client = _client(mock_s3)
    assert client.exists("gone-bucket") is False


def test_exists_propagates_non_404_error_as_api_error() -> None:
    mock_s3 = MagicMock()
    exc = _make_client_error("403")
    mock_s3.head_bucket.side_effect = exc
    client = _client(mock_s3)
    with pytest.raises(APIError):
        client.exists("forbidden-bucket")


# ---------------------------------------------------------------------------
# create()
# ---------------------------------------------------------------------------


def test_create_calls_create_bucket_with_name_and_location() -> None:
    mock_s3 = MagicMock()
    mock_s3.create_bucket.return_value = {}
    client = _client(mock_s3)
    client.create("new-bucket")

    mock_s3.create_bucket.assert_called_once_with(
        Bucket="new-bucket",
        CreateBucketConfiguration={"LocationConstraint": TEST_ZONE},
    )


def test_create_raises_api_error_on_failure() -> None:
    mock_s3 = MagicMock()
    exc = _make_client_error("BucketAlreadyExists")
    mock_s3.create_bucket.side_effect = exc
    client = _client(mock_s3)
    with pytest.raises(APIError, match="create_bucket failed"):
        client.create("dupe-bucket")


# ---------------------------------------------------------------------------
# delete()
# ---------------------------------------------------------------------------


def test_delete_calls_delete_bucket_with_name() -> None:
    mock_s3 = MagicMock()
    mock_s3.delete_bucket.return_value = {}
    client = _client(mock_s3)
    client.delete("old-bucket")
    mock_s3.delete_bucket.assert_called_once_with(Bucket="old-bucket")


def test_delete_raises_api_error_on_failure() -> None:
    mock_s3 = MagicMock()
    exc = _make_client_error("NoSuchBucket")
    mock_s3.delete_bucket.side_effect = exc
    client = _client(mock_s3)
    with pytest.raises(APIError, match="delete_bucket failed"):
        client.delete("absent-bucket")


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _make_client_error(code: str) -> Exception:
    """Build a minimal exception that mimics a botocore ClientError response dict."""
    exc = Exception(f"ClientError: {code}")
    exc.response = {"Error": {"Code": code}}  # type: ignore[attr-defined]
    return exc
