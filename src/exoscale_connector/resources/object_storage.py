"""Object Storage (SOS) resource client.

Exoscale SOS is S3-compatible and is **not** part of the APIv2.  It uses S3
SigV4 authentication (not the EXO2-HMAC signer), so this module wraps
``boto3`` directly rather than using :class:`~exoscale_connector.client.ExoscaleClient`.

``boto3`` is an *optional* dependency installed via the ``[sos]`` extra::

    pip install 'exoscale-connector[sos]'

The same Exoscale API key / secret pair used for APIv2 is used as the S3
credentials (``aws_access_key_id`` / ``aws_secret_access_key``).  The SOS
endpoint for a zone follows the pattern ``https://sos-{zone}.exo.io``.

Lazy import
-----------
``boto3`` is imported inside :meth:`BucketClient.__init__` (or on first use
when an injected client is provided), so the module itself can be imported
without ``boto3`` installed.  Tests inject a mock via the ``s3_client``
constructor parameter and never trigger the real import.
"""
from __future__ import annotations

from typing import Any, List, Optional

from ..config import ClientConfig
from ..errors import APIError, ConfigError
from ..models import ExoscaleModel


def _sos_endpoint(zone: str) -> str:
    """Return the SOS S3-compatible endpoint for *zone*."""
    return f"https://sos-{zone}.exo.io"


class Bucket(ExoscaleModel):
    """A single SOS bucket as returned by the S3 ListBuckets response."""

    name: Optional[str] = None
    # S3 returns an ISO-8601 string; kept as a plain string to avoid the
    # datetime-parsing complexity and stay consistent with the rest of the library.
    creation_date: Optional[str] = None


def _build_s3_client(config: ClientConfig, zone: str) -> Any:
    """Build a real boto3 S3 client pointed at the SOS endpoint.

    Raises :class:`~exoscale_connector.errors.ConfigError` if boto3 is not
    installed (directing the caller to install the ``[sos]`` extra).
    """
    try:
        import boto3  # type: ignore[import-not-found,import-untyped]  # noqa: PLC0415
    except ImportError as exc:
        raise ConfigError(
            "boto3 is required for Object Storage (SOS) support. "
            "Install it with: pip install 'exoscale-connector[sos]'"
        ) from exc

    return boto3.client(
        "s3",
        endpoint_url=_sos_endpoint(zone),
        aws_access_key_id=config.api_key,
        aws_secret_access_key=config.api_secret,
        region_name=zone,
    )


class BucketClient:
    """Manage Exoscale SOS buckets via the S3-compatible API.

    Parameters
    ----------
    config:
        Connector config supplying API credentials and zone.
    zone:
        Exoscale zone (e.g. ``"de-fra-1"``).  Overrides ``config.zone`` when
        given.  Required if ``config.zone`` is not set and no ``s3_client`` is
        injected.
    s3_client:
        Inject a pre-built (or mock) S3 client.  When provided no boto3 import
        occurs and *zone* is only needed for ``_sos_endpoint`` resolution (which
        is bypassed too).  Useful for unit testing without boto3 installed.
    """

    def __init__(
        self,
        config: ClientConfig,
        *,
        zone: Optional[str] = None,
        s3_client: Optional[Any] = None,
    ) -> None:
        self._config = config
        self._zone: Optional[str] = zone or config.zone

        if s3_client is not None:
            self._s3: Any = s3_client
        else:
            # Require zone when we need to build the real endpoint.
            if not self._zone:
                raise ConfigError(
                    "A zone is required for SOS: set EXOSCALE_ZONE, pass zone=..., "
                    "or inject an s3_client for testing."
                )
            self._s3 = _build_s3_client(config, self._zone)

    # ------------------------------------------------------------------ #
    # Read
    # ------------------------------------------------------------------ #

    def list(self) -> List[Bucket]:
        """Return all buckets visible to the configured credentials."""
        response = self._s3.list_buckets()
        raw_buckets = response.get("Buckets") or []
        result: List[Bucket] = []
        for item in raw_buckets:
            creation = item.get("CreationDate")
            result.append(
                Bucket(
                    name=item.get("Name"),
                    creation_date=str(creation) if creation is not None else None,
                )
            )
        return result

    def exists(self, name: str) -> bool:
        """Return ``True`` if the bucket exists and is accessible.

        Uses ``HeadBucket``; returns ``False`` on a 404 / ``NoSuchBucket`` error.
        Propagates other errors (e.g. permission denied) as :class:`APIError`.
        """
        try:
            self._s3.head_bucket(Bucket=name)
            return True
        except Exception as exc:  # noqa: BLE001
            error_code = _extract_error_code(exc)
            if error_code in {"404", "NoSuchBucket"}:
                return False
            raise APIError(
                f"head_bucket failed for '{name}': {exc}",
                status_code=int(error_code) if error_code.isdigit() else 0,
            ) from exc

    # ------------------------------------------------------------------ #
    # Write
    # ------------------------------------------------------------------ #

    def create(self, name: str) -> None:
        """Create a new bucket with the given *name*.

        The ``LocationConstraint`` is set to the configured zone, which is
        required by the SOS S3-compatible API.

        Raises :class:`APIError` on failure.
        """
        zone = self._zone or ""
        kwargs: dict = {"Bucket": name}
        if zone:
            kwargs["CreateBucketConfiguration"] = {"LocationConstraint": zone}
        try:
            self._s3.create_bucket(**kwargs)
        except Exception as exc:  # noqa: BLE001
            error_code = _extract_error_code(exc)
            raise APIError(
                f"create_bucket failed for '{name}': {exc}",
                status_code=int(error_code) if error_code.isdigit() else 0,
            ) from exc

    def delete(self, name: str) -> None:
        """Delete the bucket with the given *name*.

        Raises :class:`APIError` on failure (the bucket must be empty first).
        """
        try:
            self._s3.delete_bucket(Bucket=name)
        except Exception as exc:  # noqa: BLE001
            error_code = _extract_error_code(exc)
            raise APIError(
                f"delete_bucket failed for '{name}': {exc}",
                status_code=int(error_code) if error_code.isdigit() else 0,
            ) from exc


# ------------------------------------------------------------------ #
# Helpers
# ------------------------------------------------------------------ #

def _extract_error_code(exc: Exception) -> str:
    """Extract an S3 error code string from a botocore ``ClientError``, or '0'."""
    # botocore.exceptions.ClientError carries response metadata without
    # requiring botocore to be imported here.
    response = getattr(exc, "response", None)
    if isinstance(response, dict):
        error = response.get("Error") or {}
        code = error.get("Code") or error.get("HTTPStatusCode") or ""
        return str(code)
    return "0"
