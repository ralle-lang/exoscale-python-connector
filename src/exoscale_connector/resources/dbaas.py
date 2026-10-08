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
from typing import Any

from ..errors import NotFoundError
from ..models import ExoscaleModel, Operation
from ._base import ResourceClient, _looks_like_operation


class DBaaSConnectionInfo(ExoscaleModel):
    """Connection parameters embedded in a service detail response.

    All fields are optional because the API omits them on list responses
    (only the item endpoint returns full details).
    """

    # Host/port/user/dbname for direct connection (Aiven uri-params shape).
    host: str | None = None
    port: int | None = None
    user: str | None = None
    dbname: str | None = None
    # Aiven PEM CA cert for TLS verification (a single PEM-encoded string).
    ca: str | None = None
    # Raw connection URI(s). The shape is per engine: a LIST for PostgreSQL
    # (primary + read replicas — verified against the live API) and the other
    # data engines, but a single string for Grafana.
    uri: str | list[str] | None = None


class DBaaSService(ExoscaleModel):
    """An Exoscale managed database service.

    Only the fields common to all service types are declared here.  All
    extra type-specific fields (e.g. ``pg-settings``, ``maintenance``) pass
    through transparently because ``ExoscaleModel`` uses ``extra="allow"``.
    """

    # DBaaS uses the service name as its identifier — there is no separate UUID.
    name: str | None = None
    # Service type string returned by the API: "pg", "mysql", "redis", etc.
    type: str | None = None
    plan: str | None = None
    state: str | None = None
    # Engine version. Settable on update for engines that support version
    # upgrades (mysql, valkey, clickhouse, pg, ...) via the type-specific PUT;
    # round-tripped on the type-specific GET.
    version: str | None = None
    # Number of nodes in the cluster.
    node_count: int | None = None
    # Allocated disk size in megabytes.
    disk_size: int | None = None
    # IP allow-list (CIDR strings) for incoming connections. Settable via the
    # create/update payload and returned on the type-specific GET for every
    # service type. Absent or empty means allow-all. Since a managed DB can't
    # join a private network, this plus TLS is the primary way to secure it.
    ip_filter: list[str] | None = None
    # ISO-8601 creation timestamp.
    created_at: str | None = None
    # Structured connection parameters (full item endpoint only).
    uri_params: DBaaSConnectionInfo | None = None
    # Short connection URI string, if returned.
    uri: str | None = None
    # Connection details including CA cert (full item endpoint only).
    connection_info: DBaaSConnectionInfo | None = None


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
    _URL_TYPE_ALIASES: dict[str, str] = {"pg": "postgres"}

    @classmethod
    def _url_type(cls, service_type: str) -> str:
        """Translate a service-type alias to the form the URL expects."""
        return cls._URL_TYPE_ALIASES.get(service_type, service_type)

    def get(  # type: ignore[override]
        self,
        resource_id: str,
        *,
        zone: str | None = None,
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

    def _settle(self, response: Any, *, zone: str | None, wait: bool | None) -> Any:
        """Await an operation envelope (the spec's response for DBaaS mutations).

        Returns the settled envelope as a dict, or ``response`` unchanged when it
        is not an operation. A settled operation does not mean the service is
        ``running`` — it moves through ``rebuilding`` first; use
        :meth:`wait_for_state` for that.
        """
        if not isinstance(response, dict) or not _looks_like_operation(response):
            return response
        operation = Operation.model_validate(response)
        if self._should_wait(wait) and operation.id:
            operation = self.client.wait_operation(operation, zone=zone)
        return operation.model_dump(by_alias=True, exclude_none=True)

    def create(  # type: ignore[override]
        self,
        payload: Any,
        *,
        service_type: str,
        name: str,
        zone: str | None = None,
        wait: bool | None = None,
    ) -> DBaaSService:
        """Create a managed database service and return it.

        ``service_type`` (e.g. ``"pg"``, ``"mysql"``, ``"redis"``) determines
        which type-specific endpoint to call:
        ``POST dbaas-{service_type}/{name}``.

        The spec has the POST answer with an operation, which is awaited by
        default (``wait=False`` skips that); the service is then re-fetched for
        a consistently typed model.

        Args:
            payload: Service configuration as a dict or pydantic model.
                     Does *not* need to include ``name`` — that is encoded in
                     the URL path.
            service_type: Exoscale service type identifier, e.g. ``"pg"``.
            name: The desired service name (becomes part of the URL path).
            zone: Target zone, overrides the client default.
            wait: Await the create operation (default: the client's
                  ``wait_for_operations``).
        """
        zone = self._zone(zone)
        body: dict[str, Any] = {}
        if isinstance(payload, dict):
            body = {k: v for k, v in payload.items() if v is not None}
        elif hasattr(payload, "model_dump"):
            body = payload.model_dump(by_alias=True, exclude_none=True)

        # Type-specific create endpoint: POST dbaas-{url-type}/{name}
        url_path = f"dbaas-{self._url_type(service_type)}/{name}"
        self._settle(self.client.post(url_path, zone=zone, json=body or None), zone=zone, wait=wait)
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
        zone: str | None = None,
        wait: bool | None = None,
    ) -> DBaaSService:
        """Update a service (``PUT dbaas-{type}/{name}``) and return its new state.

        This is the path for plan changes, maintenance-window configuration
        (``{"maintenance": {"dow": "sunday", "time": "04:00:00"}}``) and
        type-specific settings (``pg-settings`` etc.). The update operation is
        awaited by default, then the service is re-fetched for a consistently
        typed result.

        Live-verified 2026-06-10 (tier-4 pg lifecycle, maintenance-window
        update).
        """
        zone = self._zone(zone)
        body: dict[str, Any] = {}
        if isinstance(payload, dict):
            body = {k: v for k, v in payload.items() if v is not None}
        elif hasattr(payload, "model_dump"):
            body = payload.model_dump(by_alias=True, exclude_none=True)
        url_path = f"dbaas-{self._url_type(service_type)}/{name}"
        self._settle(self.client.put(url_path, zone=zone, json=body or None), zone=zone, wait=wait)
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
        zone: str | None = None,
        wait: bool | None = None,
    ) -> dict:
        """Create a database user (``POST dbaas-{type}/{name}/user``).

        Returns the settled operation envelope as a dict. Retrieve the
        password afterwards with :meth:`reveal_user_password` — and treat it
        as the secret it is.

        Live-verified 2026-06-10 (tier-4 pg lifecycle).
        """
        zone = self._zone(zone)
        response = self.client.post(
            f"dbaas-{self._url_type(service_type)}/{name}/user",
            zone=zone,
            json={"username": username},
        )
        return self._settle(response, zone=zone, wait=wait)

    def delete_user(
        self,
        name: str,
        username: str,
        *,
        service_type: str,
        zone: str | None = None,
        wait: bool | None = None,
    ) -> dict:
        """Delete a database user (``DELETE dbaas-{type}/{name}/user/{username}``).

        Live-verified 2026-06-10 (tier-4 pg lifecycle).

        .. warning::
           **ClickHouse is out of scope and unverified** (roadmap D4 — it is not
           enabled on a default tenant, so it cannot be exercised here). Upstream
           moved this endpoint to
           ``DELETE /dbaas-clickhouse/{name}/user/{user-uuid}`` — the path
           parameter was renamed *and* retyped to a UUID, and ClickHouse does
           carry a per-user ``uuid`` (its ``password/reset`` and
           ``password/reveal`` endpoints still take a username, as does
           ``delete`` on every other engine). This method interpolates whatever
           you pass, so a username may no longer resolve for
           ``service_type="clickhouse"``. Nothing here changed because the spec
           alone does not settle it (D1) and the connector exposes no user
           listing to obtain the uuid from. Live verification was attempted
           2026-08-01 and is blocked: ClickHouse is not enabled on the test
           tenant (``403 "... not enabled"`` on every ClickHouse operation,
           including read-only ones), which is what put the engine out of
           scope. Every other engine deletes by username as documented.
        """
        zone = self._zone(zone)
        response = self.client.delete(
            f"dbaas-{self._url_type(service_type)}/{name}/user/{username}", zone=zone
        )
        return self._settle(response, zone=zone, wait=wait)

    def reset_user_password(
        self,
        name: str,
        username: str,
        *,
        service_type: str,
        zone: str | None = None,
        wait: bool | None = None,
    ) -> dict:
        """Reset a user's password (``PUT .../user/{username}/password/reset``).

        The new password is *not* returned here — fetch it afterwards with
        :meth:`reveal_user_password`.

        .. warning::
           Implemented from the API reference — pending live verification.
        """
        zone = self._zone(zone)
        response = self.client.put(
            f"dbaas-{self._url_type(service_type)}/{name}/user/{username}/password/reset",
            zone=zone,
        )
        return self._settle(response, zone=zone, wait=wait)

    def get_connection_info(
        self,
        name: str,
        *,
        service_type: str,
        zone: str | None = None,
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
        zone: str | None = None,
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

    # ------------------------------------------------------------------ #
    # Generic engine sub-resources (settings / ACL / maintenance)
    # ------------------------------------------------------------------ #

    def get_settings(self, service_type: str, *, zone: str | None = None) -> dict:
        """Return the configurable settings schema for an engine type.

        Wraps ``GET /dbaas-settings-{type}`` — the discovery endpoint that
        describes which ``{type}-settings`` keys a service accepts (e.g.
        ``clickhouse-settings``, ``mysql-settings``) and their constraints.

        Note this endpoint uses the **short** service-type form (``pg``, not
        ``postgres``) — the same names :meth:`list_service_types` returns —
        unlike the type-specific CRUD paths which use the long form. The
        response schema is engine-specific, so a raw dict is returned.
        """
        return self.client.get(f"dbaas-settings-{service_type}", zone=self._zone(zone))

    def get_acl_config(self, name: str, *, service_type: str, zone: str | None = None) -> dict:
        """Return the ACL configuration for a service.

        Wraps ``GET /dbaas-{type}/{name}/acl-config``. Supported by the engines
        that expose per-user/topic ACLs (clickhouse, kafka, opensearch). The
        response schema is engine-specific, so a raw dict is returned.
        """
        return self.client.get(
            f"dbaas-{self._url_type(service_type)}/{name}/acl-config",
            zone=self._zone(zone),
        )

    def start_maintenance(
        self,
        name: str,
        *,
        service_type: str,
        zone: str | None = None,
        wait: bool | None = None,
    ) -> dict:
        """Trigger the service's pending maintenance update immediately.

        Wraps ``PUT /dbaas-{type}/{name}/maintenance/start`` (available for
        every engine). Runs the maintenance that would otherwise wait for the
        configured window; returns the settled operation envelope as a dict
        (``wait=False`` returns it unawaited).
        """
        zone = self._zone(zone)
        response = self.client.put(
            f"dbaas-{self._url_type(service_type)}/{name}/maintenance/start", zone=zone
        )
        return self._settle(response, zone=zone, wait=wait)

    def list_service_types(self, *, zone: str | None = None) -> list[dict]:
        """Return available DBaaS service types from the ``dbaas-service-type`` endpoint.

        The response schema is type-specific so we return raw dicts rather than
        a typed model.
        """
        payload = self.client.get("dbaas-service-type", zone=self._zone(zone))
        items = payload.get("dbaas-service-types") or []
        return [i for i in items if isinstance(i, dict)]
