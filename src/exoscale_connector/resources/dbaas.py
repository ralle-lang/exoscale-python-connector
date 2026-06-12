"""DBaaS (managed database) resource client.

The Exoscale DBaaS API is unlike other asset types in two ways:

1. **Resources are identified by name**, not UUID.  The collection endpoint
   ``dbaas-service`` lists all services, but CRUD operations use the service
   *name* as the path token.

2. **Endpoints are service-type-specific for mutations.** Create and update hit
   ``dbaas-{type}/{name}`` (e.g. ``dbaas-pg/my-db``), while the generic get
   ``dbaas-service/{name}`` and delete ``dbaas-service/{name}`` work across
   types.

API reference: https://openapi-v2.exoscale.com/#tag/DBaaS
"""
from __future__ import annotations

import random
import time
from typing import Any, Dict, List, Optional

from ..errors import NotFoundError
from ..models import ExoscaleModel
from ._base import ResourceClient


class DBaaSConnectionInfo(ExoscaleModel):
    """Connection parameters embedded in a service detail response.

    All fields are optional because the API omits them on list responses
    (only the item endpoint returns full details).
    """

    # Host/port/user/dbname for direct connection (Aiven uri-params shape).
    host: Optional[str] = None
    port: Optional[int] = None
    user: Optional[str] = None
    dbname: Optional[str] = None
    # Aiven PEM CA cert for TLS verification (a single PEM-encoded string).
    ca: Optional[str] = None
    # Raw connection URI(s). The API returns this as a LIST for PostgreSQL
    # (primary + read replicas), not a string — verified against the live API.
    uri: Optional[List[str]] = None


class DBaaSService(ExoscaleModel):
    """An Exoscale managed database service.

    Only the fields common to all service types are declared here.  All
    extra type-specific fields (e.g. ``pg-settings``, ``maintenance``) pass
    through transparently because ``ExoscaleModel`` uses ``extra="allow"``.
    """

    # DBaaS uses the service name as its identifier — there is no separate UUID.
    name: Optional[str] = None
    # Service type string returned by the API: "pg", "mysql", "redis", etc.
    type: Optional[str] = None
    plan: Optional[str] = None
    state: Optional[str] = None
    # Number of nodes in the cluster.
    node_count: Optional[int] = None
    # Allocated disk size in megabytes.
    disk_size: Optional[int] = None
    # IP allow-list (CIDR strings) for incoming connections. Settable via the
    # create/update payload and returned on the type-specific GET for every
    # service type. Absent or empty means allow-all. Since a managed DB can't
    # join a private network, this plus TLS is the primary way to secure it.
    ip_filter: Optional[List[str]] = None
    # ISO-8601 creation timestamp.
    created_at: Optional[str] = None
    # Structured connection parameters (full item endpoint only).
    uri_params: Optional[DBaaSConnectionInfo] = None
    # Short connection URI string, if returned.
    uri: Optional[str] = None
    # Connection details including CA cert (full item endpoint only).
    connection_info: Optional[DBaaSConnectionInfo] = None


class DBaaSServiceClient(ResourceClient[DBaaSService]):
    """Manage Exoscale DBaaS (managed database) services.

    Key differences from a standard asset client:

    * ``id_field`` and ``name_field`` are both ``"name"`` — the service name
      is the unique identifier.
    * :meth:`get` uses the generic ``dbaas-service/{name}`` endpoint, which
      works across all service types.
    * :meth:`create` requires an explicit ``service_type`` because the create
      endpoint is type-specific (``POST dbaas-{type}/{name}``).  After the
      create call returns the client re-fetches the service by name.
    * :meth:`delete` inherits from the base and hits ``dbaas-service/{name}``.

    Service-type name aliasing: Exoscale's API uses *short* names in
    ``list_service_types`` (``pg``, ``mysql``, ``valkey`` …) but *long* names
    in the type-specific URL paths (``postgres``, ``mysql`` …). The only
    mismatch in current use is ``pg → postgres`` — every other short name is
    identical to its URL form. :attr:`_URL_TYPE_ALIASES` translates at the
    URL boundary so callers can pass either form.
    """

    collection_path = "dbaas-service"
    model = DBaaSService
    list_key = "dbaas-services"
    id_field = "name"
    name_field = "name"

    # Short-form → URL-form mapping for known mismatches.
    _URL_TYPE_ALIASES: Dict[str, str] = {"pg": "postgres"}

    @classmethod
    def _url_type(cls, service_type: str) -> str:
        """Translate a service-type alias to the form the URL expects."""
        return cls._URL_TYPE_ALIASES.get(service_type, service_type)

    def get(  # type: ignore[override]
        self,
        resource_id: str,
        *,
        zone: Optional[str] = None,
    ) -> DBaaSService:
        """Fetch a DBaaS service by name.

        Unlike every other asset type, ``GET /dbaas-service/{name}`` returns
        404 — that path is list-only on Exoscale's APIv2. To fetch a single
        service we therefore have to:

        1. ``GET /dbaas-service`` to discover the service's ``type``.
        2. ``GET /dbaas-{long-type}/{name}`` for the actual detail body.

        Slightly costlier than other types (two requests instead of one) but
        keeps ``get(name)`` working as callers would expect from the rest of
        the connector.
        """
        zone_eff = self._zone(zone)
        listing = self.client.get(self.collection_path, zone=zone_eff)
        match = next(
            (
                s
                for s in listing.get(self.list_key) or []
                if isinstance(s, dict) and s.get("name") == resource_id
            ),
            None,
        )
        if match is None:
            raise NotFoundError(
                f"DBaaS service {resource_id!r} not found",
                status_code=404,
                payload={},
                method="GET",
                url=f"{self.collection_path}/{resource_id}",
            )
        svc_type = match.get("type")
        if not svc_type:
            # No type advertised — return what we have from the listing.
            return self.model.model_validate(match)
        payload = self.client.get(
            f"dbaas-{self._url_type(str(svc_type))}/{resource_id}",
            zone=zone_eff,
        )
        return self.model.model_validate(payload)

    # The DBaaS API does not return an async operation on create; the service
    # is either ready or still building when the POST resolves.  We do not wait
    # for a separate operation object.
    wait_for_operations: bool = False

    def create(  # type: ignore[override]
        self,
        payload: Any,
        *,
        service_type: str,
        name: str,
        zone: Optional[str] = None,
        wait: Optional[bool] = None,
    ) -> DBaaSService:
        """Create a managed database service and return it.

        ``service_type`` (e.g. ``"pg"``, ``"mysql"``, ``"redis"``) determines
        which type-specific endpoint to call:
        ``POST dbaas-{service_type}/{name}``.

        The create endpoint returns the service body directly (no async
        operation), so after the POST resolves the client re-fetches via
        :meth:`get` to return a consistently typed model.

        Args:
            payload: Service configuration as a dict or pydantic model.
                     Does *not* need to include ``name`` — that is encoded in
                     the URL path.
            service_type: Exoscale service type identifier, e.g. ``"pg"``.
            name: The desired service name (becomes part of the URL path).
            zone: Target zone, overrides the client default.
            wait: Unused for DBaaS (no async operation), accepted for API
                  consistency with other clients.
        """
        zone = self._zone(zone)
        body: Dict[str, Any] = {}
        if isinstance(payload, dict):
            body = {k: v for k, v in payload.items() if v is not None}
        elif hasattr(payload, "model_dump"):
            body = payload.model_dump(by_alias=True, exclude_none=True)

        # Type-specific create endpoint: POST dbaas-{url-type}/{name}
        url_path = f"dbaas-{self._url_type(service_type)}/{name}"
        self.client.post(url_path, zone=zone, json=body or None)
        # Re-fetch via the SAME type-specific endpoint. The generic
        # ``dbaas-service/{name}`` is list-only — GETting an individual service
        # there always returns 404 (verified empirically). Retry briefly to
        # cover the case where the create-then-get races propagation.
        deadline = time.time() + 30
        while True:
            try:
                payload = self.client.get(url_path, zone=zone)
                return self.model.model_validate(payload)
            except NotFoundError:
                if time.time() >= deadline:
                    raise
                # Jittered so a fleet creating services concurrently doesn't
                # hammer the endpoint in lockstep.
                time.sleep(random.uniform(1.0, 3.0))

    def ensure(self, payload: Any, **kwargs: Any) -> DBaaSService:  # type: ignore[override]
        """Not supported: DBaaS ``create`` needs ``service_type``/``name`` kwargs.

        Use ``get_or_none(name)`` + :meth:`create` explicitly instead.
        """
        raise NotImplementedError(
            "DBaaSServiceClient does not support ensure(); use get_or_none(name) "
            "and create(payload, service_type=..., name=...) explicitly"
        )

    def update(  # type: ignore[override]
        self,
        name: str,
        payload: Any,
        *,
        service_type: str,
        zone: Optional[str] = None,
        wait: Optional[bool] = None,
    ) -> DBaaSService:
        """Update a service (``PUT dbaas-{type}/{name}``) and return its new state.

        This is the path for plan changes, maintenance-window configuration
        (``{"maintenance": {"dow": "sunday", "time": "04:00:00"}}``) and
        type-specific settings (``pg-settings`` etc.). Like create, the DBaaS
        API answers directly without an async operation; the service is
        re-fetched after the PUT for a consistently typed result.

        Live-verified 2026-06-10 (tier-4 pg lifecycle, maintenance-window
        update).
        """
        zone = self._zone(zone)
        body: Dict[str, Any] = {}
        if isinstance(payload, dict):
            body = {k: v for k, v in payload.items() if v is not None}
        elif hasattr(payload, "model_dump"):
            body = payload.model_dump(by_alias=True, exclude_none=True)
        url_path = f"dbaas-{self._url_type(service_type)}/{name}"
        self.client.put(url_path, zone=zone, json=body or None)
        result = self.client.get(url_path, zone=zone)
        return self.model.model_validate(result)

    # ------------------------------------------------------------------ #
    # Service users
    # ------------------------------------------------------------------ #

    def create_user(
        self,
        name: str,
        username: str,
        *,
        service_type: str,
        zone: Optional[str] = None,
    ) -> dict:
        """Create a database user (``POST dbaas-{type}/{name}/user``).

        Returns the raw response dict (schema is type-specific). Retrieve the
        password afterwards with :meth:`reveal_user_password` — and treat it
        as the secret it is.

        Live-verified 2026-06-10 (tier-4 pg lifecycle).
        """
        return self.client.post(
            f"dbaas-{self._url_type(service_type)}/{name}/user",
            zone=self._zone(zone),
            json={"username": username},
        )

    def delete_user(
        self,
        name: str,
        username: str,
        *,
        service_type: str,
        zone: Optional[str] = None,
    ) -> dict:
        """Delete a database user (``DELETE dbaas-{type}/{name}/user/{username}``).

        Live-verified 2026-06-10 (tier-4 pg lifecycle).
        """
        return self.client.delete(
            f"dbaas-{self._url_type(service_type)}/{name}/user/{username}",
            zone=self._zone(zone),
        )

    def reset_user_password(
        self,
        name: str,
        username: str,
        *,
        service_type: str,
        zone: Optional[str] = None,
    ) -> dict:
        """Reset a user's password (``PUT .../user/{username}/password/reset``).

        The new password is *not* returned here — fetch it afterwards with
        :meth:`reveal_user_password`.

        .. warning::
           Implemented from the API reference — pending live verification.
        """
        return self.client.put(
            f"dbaas-{self._url_type(service_type)}/{name}/user/{username}/password/reset",
            zone=self._zone(zone),
        )

    def get_connection_info(
        self,
        name: str,
        *,
        service_type: str,
        zone: Optional[str] = None,
    ) -> DBaaSService:
        """Fetch the full service detail including ``connection-info`` and ``uri-params``.

        The generic ``dbaas-service/{name}`` list/get endpoint omits connection
        parameters on some API versions.  Use the type-specific endpoint
        ``dbaas-{type}/{name}`` to ensure the full detail is returned.

        Args:
            name: Service name.
            service_type: Exoscale service type string, e.g. ``"pg"``.
            zone: Target zone.
        """
        payload = self.client.get(
            f"dbaas-{self._url_type(service_type)}/{name}",
            zone=self._zone(zone),
        )
        return self.model.model_validate(payload)

    def reveal_user_password(
        self,
        name: str,
        username: str,
        *,
        service_type: str,
        zone: Optional[str] = None,
    ) -> dict:
        """Return the revealed credentials for a service user.

        Calls ``GET dbaas-{type}/{name}/user/{username}/password/reveal``.
        The response is returned as a raw dict (the schema is type-specific
        and varies between pg, mysql, etc.).

        .. warning::
           The returned dict contains a live password in clear text. Treat it
           like any other secret — never log it or print it in CI output.

        Args:
            name: Service name.
            username: The user whose password should be revealed.
            service_type: Exoscale service type string, e.g. ``"pg"``.
            zone: Target zone.
        """
        return self.client.get(
            f"dbaas-{self._url_type(service_type)}/{name}/user/{username}/password/reveal",
            zone=self._zone(zone),
        )

    def list_service_types(self, *, zone: Optional[str] = None) -> List[dict]:
        """Return available DBaaS service types from the ``dbaas-service-type`` endpoint.

        The response schema is type-specific so we return raw dicts rather than
        a typed model.
        """
        payload = self.client.get("dbaas-service-type", zone=self._zone(zone))
        items = payload.get("dbaas-service-types") or []
        return [i for i in items if isinstance(i, dict)]
