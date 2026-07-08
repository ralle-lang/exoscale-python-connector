"""KMS (Key Management Service) resource client.

Manages Exoscale-managed encryption keys (`/kms-key`) and the operations around
them: lifecycle (create / enable / disable), rotation, envelope crypto
(encrypt / decrypt / re-encrypt / generate-data-key), a deferred deletion
lifecycle (schedule / cancel), and cross-zone replication.

Two things set KMS apart from a standard asset type:

1. **No immediate delete.** There is no ``DELETE /kms-key/{id}``; a key is
   removed by scheduling a deletion (:meth:`KmsKeyClient.schedule_deletion`),
   which starts a waiting period you can still cancel
   (:meth:`KmsKeyClient.cancel_deletion`). :meth:`delete` therefore raises.
2. **Synchronous.** Unlike most asset types, KMS endpoints do not return async
   operation envelopes — create returns the key directly and the sub-operations
   return their result immediately.

.. warning::
   The crypto methods take and return **secret material** (plaintext, data
   keys). They are library-only by design — never exposed on the CLI, where
   arguments leak into the process list. Never log or print their return values.

API reference: https://openapi-v2.exoscale.com/group/endpoint-kms
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from ..models import ExoscaleModel
from ._base import ResourceClient


class KeyRotationConfig(ExoscaleModel):
    """A key's rotation configuration."""

    automatic: Optional[bool] = None
    manual_count: Optional[int] = None
    next_at: Optional[str] = None
    rotation_period: Optional[int] = None


class KmsKey(ExoscaleModel):
    """An Exoscale-managed KMS key.

    Fields mirror the detail response (``GET /kms-key/{id}``); ``material``,
    ``revision`` and ``replicas_status`` are passed through as raw structures
    since callers rarely need them typed.
    """

    id: Optional[str] = None
    name: Optional[str] = None
    description: Optional[str] = None
    # "enabled" | "disabled" | "pending-deletion"
    status: Optional[str] = None
    status_since: Optional[str] = None
    # Set once a deletion is scheduled; cleared by cancel-deletion.
    delete_at: Optional[str] = None
    usage: Optional[str] = None  # "encrypt-decrypt"
    source: Optional[str] = None  # "exoscale-kms"
    multi_zone: Optional[bool] = None
    origin_zone: Optional[str] = None
    material: Optional[Dict[str, Any]] = None
    revision: Optional[Dict[str, Any]] = None
    rotation: Optional[KeyRotationConfig] = None
    replicas: Optional[List[str]] = None
    replicas_status: Optional[List[Dict[str, Any]]] = None
    created_at: Optional[str] = None


class KmsKeyClient(ResourceClient[KmsKey]):
    """Manage KMS keys, their rotation, crypto operations, and lifecycle.

    ``list`` / ``get`` / ``create`` use the inherited verbs (KMS is synchronous,
    so no operation waiting is involved). Everything else is a dedicated method
    because KMS exposes colon-free sub-action endpoints rather than the standard
    CRUD verbs.
    """

    collection_path = "kms-key"
    model = KmsKey
    list_key = "kms-keys"
    # KMS is synchronous — endpoints return results directly, not async ops.
    wait_for_operations: bool = False

    def delete(self, *args: Any, **kwargs: Any) -> Any:  # type: ignore[override]
        """Not supported — KMS keys have no immediate delete.

        Use :meth:`schedule_deletion` (which starts a cancellable waiting
        period) and, if needed, :meth:`cancel_deletion`.
        """
        raise NotImplementedError(
            "KMS keys cannot be deleted immediately; use schedule_deletion() "
            "(cancellable via cancel_deletion())"
        )

    # ------------------------------------------------------------------ #
    # State
    # ------------------------------------------------------------------ #

    def enable(self, key_id: str, *, zone: Optional[str] = None) -> dict:
        """Enable a key (``POST /kms-key/{id}/enable``). Returns ``{"status": ...}``."""
        return self.client.post(
            f"{self.collection_path}/{key_id}/enable", zone=self._zone(zone)
        )

    def disable(self, key_id: str, *, zone: Optional[str] = None) -> dict:
        """Disable a key (``POST /kms-key/{id}/disable``). A disabled key can't decrypt."""
        return self.client.post(
            f"{self.collection_path}/{key_id}/disable", zone=self._zone(zone)
        )

    # ------------------------------------------------------------------ #
    # Rotation
    # ------------------------------------------------------------------ #

    def enable_rotation(
        self,
        key_id: str,
        *,
        rotation_period: Optional[int] = None,
        zone: Optional[str] = None,
    ) -> dict:
        """Enable automatic rotation (``POST .../enable-key-rotation``).

        ``rotation_period`` is the interval in days; omit it for the API default.
        Returns the updated ``{"rotation": {...}}`` config.
        """
        body = {"rotation-period": rotation_period} if rotation_period is not None else None
        return self.client.post(
            f"{self.collection_path}/{key_id}/enable-key-rotation",
            zone=self._zone(zone),
            json=body,
        )

    def disable_rotation(self, key_id: str, *, zone: Optional[str] = None) -> dict:
        """Disable automatic rotation (``POST .../disable-key-rotation``)."""
        return self.client.post(
            f"{self.collection_path}/{key_id}/disable-key-rotation", zone=self._zone(zone)
        )

    def rotate(self, key_id: str, *, zone: Optional[str] = None) -> dict:
        """Rotate the key material now (``POST .../rotate``). Returns the new rotation state."""
        return self.client.post(
            f"{self.collection_path}/{key_id}/rotate", zone=self._zone(zone)
        )

    def list_rotations(self, key_id: str, *, zone: Optional[str] = None) -> List[dict]:
        """List a key's past rotations (``GET .../list-key-rotations``)."""
        payload = self.client.get(
            f"{self.collection_path}/{key_id}/list-key-rotations", zone=self._zone(zone)
        )
        rotations = payload.get("rotations") or []
        return [r for r in rotations if isinstance(r, dict)]

    # ------------------------------------------------------------------ #
    # Crypto (library-only — secret-bearing; never log/print the results)
    # ------------------------------------------------------------------ #

    def encrypt(
        self,
        key_id: str,
        plaintext: str,
        *,
        encryption_context: Optional[str] = None,
        zone: Optional[str] = None,
    ) -> dict:
        """Encrypt ``plaintext`` under the key (``POST .../encrypt``).

        ``plaintext`` and the returned ``ciphertext`` are Base64-encoded.
        ``encryption_context`` (optional, Base64) is additional authenticated
        data that must match on decrypt.

        .. warning:: ``plaintext`` is secret — never pass it via the shell/CLI.
        """
        body: Dict[str, Any] = {"plaintext": plaintext}
        if encryption_context is not None:
            body["encryption-context"] = encryption_context
        return self.client.post(
            f"{self.collection_path}/{key_id}/encrypt", zone=self._zone(zone), json=body
        )

    def decrypt(
        self,
        key_id: str,
        ciphertext: str,
        *,
        encryption_context: Optional[str] = None,
        zone: Optional[str] = None,
    ) -> dict:
        """Decrypt ``ciphertext`` (``POST .../decrypt``). Returns Base64 ``{"plaintext": ...}``.

        Any ``encryption_context`` used at encrypt time must be supplied again.

        .. warning:: The returned plaintext is secret — never log or print it.
        """
        body: Dict[str, Any] = {"ciphertext": ciphertext}
        if encryption_context is not None:
            body["encryption-context"] = encryption_context
        return self.client.post(
            f"{self.collection_path}/{key_id}/decrypt", zone=self._zone(zone), json=body
        )

    def re_encrypt(
        self,
        key_id: str,
        *,
        source: dict,
        destination: dict,
        zone: Optional[str] = None,
    ) -> dict:
        """Re-encrypt a payload from a source envelope to a destination one.

        ``POST .../re-encrypt``. ``source`` carries the existing ciphertext (and
        its encryption context); ``destination`` describes the new envelope.
        Returns the new ``{"ciphertext": ...}``.
        """
        return self.client.post(
            f"{self.collection_path}/{key_id}/re-encrypt",
            zone=self._zone(zone),
            json={"source": source, "destination": destination},
        )

    def generate_data_key(
        self,
        key_id: str,
        *,
        key_spec: str = "AES-256",
        bytes_count: Optional[int] = None,
        encryption_context: Optional[str] = None,
        zone: Optional[str] = None,
    ) -> dict:
        """Generate a data key (``POST .../generate-data-key``).

        Returns both the wrapped ``ciphertext`` (store this) and the ``plaintext``
        data key (use it, then discard — never persist it).

        .. warning:: The returned ``plaintext`` data key is secret — never log,
           print, or store it; keep only the ``ciphertext``.
        """
        body: Dict[str, Any] = {"key-spec": key_spec}
        if bytes_count is not None:
            body["bytes-count"] = bytes_count
        if encryption_context is not None:
            body["encryption-context"] = encryption_context
        return self.client.post(
            f"{self.collection_path}/{key_id}/generate-data-key",
            zone=self._zone(zone),
            json=body,
        )

    # ------------------------------------------------------------------ #
    # Deletion lifecycle
    # ------------------------------------------------------------------ #

    def schedule_deletion(
        self,
        key_id: str,
        *,
        delay_days: Optional[int] = None,
        zone: Optional[str] = None,
    ) -> dict:
        """Schedule a key for deletion after a waiting period (``POST .../schedule-deletion``).

        ``delay_days`` sets the waiting window (API default if omitted). The key
        moves to ``pending-deletion``; call :meth:`cancel_deletion` before the
        window elapses to abort. Returns ``{"delete-at": ...}``.
        """
        body = {"delay-days": delay_days} if delay_days is not None else None
        return self.client.post(
            f"{self.collection_path}/{key_id}/schedule-deletion",
            zone=self._zone(zone),
            json=body,
        )

    def cancel_deletion(self, key_id: str, *, zone: Optional[str] = None) -> dict:
        """Cancel a scheduled deletion (``POST .../cancel-deletion``), restoring the key."""
        return self.client.post(
            f"{self.collection_path}/{key_id}/cancel-deletion", zone=self._zone(zone)
        )

    # ------------------------------------------------------------------ #
    # Replication
    # ------------------------------------------------------------------ #

    def replicate(self, key_id: str, zone_target: str, *, zone: Optional[str] = None) -> dict:
        """Replicate a multi-zone key into another zone (``POST .../replicate``).

        ``zone_target`` is the destination zone; ``zone`` (as everywhere) is the
        zone the request is issued against. Returns ``{"status": ...}``.
        """
        return self.client.post(
            f"{self.collection_path}/{key_id}/replicate",
            zone=self._zone(zone),
            json={"zone": zone_target},
        )
