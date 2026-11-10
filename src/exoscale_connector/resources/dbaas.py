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

from pydantic import Field

from ..errors import NotFoundError
from ..models import ExoscaleModel, Operation, to_api_payload
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


class DBaaSConnectionPool(ExoscaleModel):
    """A PostgreSQL PgBouncer connection pool, as listed on the service detail."""

    name: str | None = None
    database: str | None = None
    username: str | None = None
    mode: str | None = None  # "transaction" | "statement" | "session"
    size: int | None = None
    # Carries credentials: excluded from repr so logging never echoes it.
    connection_uri: str | None = Field(default=None, repr=False)


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
    # Database names inside the service (pg and mysql, type-specific GET only).
    databases: list[str] | None = None
    # PgBouncer pools (pg only, type-specific GET only).
    connection_pools: list[DBaaSConnectionPool] | None = None


class DBaaSLogEntry(ExoscaleModel):
    """One service log line."""

    time: str | None = None
    node: str | None = None
    unit: str | None = None
    message: str | None = None


class DBaaSServiceLogs(ExoscaleModel):
    """A page of service logs; pass :attr:`offset` back to fetch the next one."""

    logs: list[DBaaSLogEntry] | None = None
    offset: str | None = None
    first_log_offset: str | None = None


class DBaaSTaskResultCode(ExoscaleModel):
    """One per-database result code of a :class:`DBaaSTask`."""

    code: str | None = None
    dbname: str | None = None


class DBaaSTask(ExoscaleModel):
    """A background check run by DBaaS (pg upgrade check, migration check)."""

    id: str | None = None
    task_type: str | None = None
    success: bool | None = None
    result: str | None = None
    result_codes: list[DBaaSTaskResultCode] | None = None
    create_time: str | None = None


class DBaaSMigrationDetail(ExoscaleModel):
    """Migration progress for one database."""

    dbname: str | None = None
    method: str | None = None
    status: str | None = None  # "running" | "syncing" | "failed" | "done"
    error: str | None = None


class DBaaSMigrationStatus(ExoscaleModel):
    """Status of a service's migration from an external source database."""

    status: str | None = None
    method: str | None = None
    error: str | None = None
    details: list[DBaaSMigrationDetail] | None = None


class DBaaSValkeyAccessControl(ExoscaleModel):
    """Valkey ACL for one user: allowed command categories, commands, keys, channels."""

    categories: list[str] | None = None
    commands: list[str] | None = None
    keys: list[str] | None = None
    channels: list[str] | None = None


class DBaaSValkeyUser(ExoscaleModel):
    """A Valkey service user with its access control."""

    username: str | None = None
    type: str | None = None
    access_control: DBaaSValkeyAccessControl | None = None


class DBaaSServiceClient(ResourceClient[DBaaSService]):
    """Manage Exoscale DBaaS (managed database) services.

    Key differences from a standard asset client:

    * ``id_field`` and ``name_field`` are both ``"name"`` — the service name
      is the unique identifier.
    * :meth:`get` lists ``dbaas-service`` to find the service's type, then
      fetches ``dbaas-{type}/{name}`` (``GET dbaas-service/{name}`` 404s).
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
    # Engines whose API exposes a database sub-resource (URL form).
    _DATABASE_ENGINES = ("postgres", "mysql")

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

    def _require_engine(self, service_type: str, engine: str, what: str) -> None:
        if self._url_type(service_type) != engine:
            raise ValueError(f"{what} applies to {engine} services only")

    def create_user(
        self,
        name: str,
        username: str,
        *,
        service_type: str,
        allow_replication: bool | None = None,
        authentication: str | None = None,
        access_control: DBaaSValkeyAccessControl | dict | None = None,
        zone: str | None = None,
        wait: bool | None = None,
    ) -> dict:
        """Create a database user (``POST dbaas-{type}/{name}/user``).

        Engine-specific options, each rejected with ``ValueError`` on the
        wrong engine:

        * ``allow_replication`` (pg) — grant the replication privilege.
        * ``authentication`` (mysql) — ``"caching_sha2_password"`` or
          ``"mysql_native_password"``.
        * ``access_control`` (valkey) — the user's ACL
          (:class:`DBaaSValkeyAccessControl` or its wire dict).

        Returns the settled operation envelope as a dict. Retrieve the
        password afterwards with :meth:`reveal_user_password` — and treat it
        as the secret it is.

        Live-verified 2026-06-10 (tier-4 pg lifecycle, username only); the
        engine-specific options are implemented from the API reference.
        """
        body: dict[str, Any] = {"username": username}
        if allow_replication is not None:
            self._require_engine(service_type, "postgres", "allow_replication")
            body["allow-replication"] = allow_replication
        if authentication is not None:
            self._require_engine(service_type, "mysql", "authentication")
            body["authentication"] = authentication
        if access_control is not None:
            self._require_engine(service_type, "valkey", "access_control")
            body["access-control"] = to_api_payload(access_control)
        zone = self._zone(zone)
        response = self.client.post(
            f"dbaas-{self._url_type(service_type)}/{name}/user", zone=zone, json=body
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
        password: str | None = None,
        authentication: str | None = None,
        zone: str | None = None,
        wait: bool | None = None,
    ) -> dict:
        """Reset a user's password (``PUT .../user/{username}/password/reset``).

        Without ``password`` the API generates one. ``authentication`` (mysql
        only) switches the authentication plugin at the same time. The new
        password is *not* returned here — fetch it afterwards with
        :meth:`reveal_user_password`. Pass ``password`` from a secret store,
        never a literal.
        """
        body: dict[str, Any] = {}
        if password is not None:
            body["password"] = password
        if authentication is not None:
            self._require_engine(service_type, "mysql", "authentication")
            body["authentication"] = authentication
        zone = self._zone(zone)
        response = self.client.put(
            f"dbaas-{self._url_type(service_type)}/{name}/user/{username}/password/reset",
            zone=zone,
            json=body or None,
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
    # Databases inside a service (pg / mysql)
    # ------------------------------------------------------------------ #

    def _database_engine(self, service_type: str) -> str:
        url_type = self._url_type(service_type)
        if url_type not in self._DATABASE_ENGINES:
            raise ValueError(
                f"service type {service_type!r} has no database sub-resource; only pg and mysql do"
            )
        return url_type

    def create_database(
        self,
        name: str,
        database_name: str,
        *,
        service_type: str,
        lc_collate: str | None = None,
        lc_ctype: str | None = None,
        zone: str | None = None,
        wait: bool | None = None,
    ) -> dict:
        """Create a database inside a pg or mysql service.

        Wraps ``POST dbaas-{type}/{name}/database``. ``lc_collate`` /
        ``lc_ctype`` set the PostgreSQL locale and are rejected for mysql. List
        the existing databases via :attr:`DBaaSService.databases` on
        :meth:`get_connection_info`. Returns the settled operation envelope.
        """
        url_type = self._database_engine(service_type)
        body: dict[str, Any] = {"database-name": database_name}
        if (lc_collate is not None or lc_ctype is not None) and url_type != "postgres":
            raise ValueError("lc_collate / lc_ctype apply to pg services only")
        if lc_collate is not None:
            body["lc-collate"] = lc_collate
        if lc_ctype is not None:
            body["lc-ctype"] = lc_ctype
        zone = self._zone(zone)
        response = self.client.post(f"dbaas-{url_type}/{name}/database", zone=zone, json=body)
        return self._settle(response, zone=zone, wait=wait)

    def delete_database(
        self,
        name: str,
        database_name: str,
        *,
        service_type: str,
        zone: str | None = None,
        wait: bool | None = None,
    ) -> dict:
        """Delete a database from a pg or mysql service.

        Wraps ``DELETE dbaas-{type}/{name}/database/{database_name}``. Returns
        the settled operation envelope.
        """
        url_type = self._database_engine(service_type)
        zone = self._zone(zone)
        response = self.client.delete(
            f"dbaas-{url_type}/{name}/database/{database_name}", zone=zone
        )
        return self._settle(response, zone=zone, wait=wait)

    # ------------------------------------------------------------------ #
    # TLS trust and observability (engine-generic)
    # ------------------------------------------------------------------ #

    def get_ca_certificate(self, *, zone: str | None = None) -> str:
        """Return the PEM CA certificate that signs DBaaS server certificates.

        Wraps ``GET /dbaas-ca-certificate``. Pin it as the trust root when
        connecting to the host from :meth:`get_connection_info` (e.g. libpq
        ``sslrootcert`` with ``sslmode=verify-full``).

        Live-verified 2026-10-08 (read-only smoke).
        """
        payload = self.client.get("dbaas-ca-certificate", zone=self._zone(zone))
        return str(payload.get("certificate") or "")

    def get_logs(
        self,
        name: str,
        *,
        limit: int | None = None,
        offset: str | None = None,
        sort_order: str | None = None,
        zone: str | None = None,
    ) -> DBaaSServiceLogs:
        """Fetch a page of service logs (``POST /dbaas-service-logs/{name}``).

        A read despite the POST. ``limit`` is 1–500 (API default 100);
        ``sort_order`` is ``"desc"`` (default) or ``"asc"``; ``offset`` is the
        opaque cursor from a previous page's :attr:`DBaaSServiceLogs.offset`.
        """
        body = {"limit": limit, "offset": offset, "sort-order": sort_order}
        payload = self.client.post(
            f"dbaas-service-logs/{name}",
            zone=self._zone(zone),
            json={k: v for k, v in body.items() if v is not None},
        )
        return DBaaSServiceLogs.model_validate(payload)

    def get_metrics(self, name: str, *, period: str | None = None, zone: str | None = None) -> dict:
        """Fetch service metrics (``POST /dbaas-service-metrics/{name}``).

        A read despite the POST. ``period`` is one of ``hour`` (API default),
        ``day``, ``week``, ``month``, ``year``. The metric series are
        engine-specific, so the ``metrics`` object is returned as a raw dict.
        """
        payload = self.client.post(
            f"dbaas-service-metrics/{name}",
            zone=self._zone(zone),
            json={"period": period} if period else {},
        )
        return dict(payload.get("metrics") or {})

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

    # ------------------------------------------------------------------ #
    # Migration from an external database (pg / mysql / valkey) and tasks
    # ------------------------------------------------------------------ #

    _MIGRATION_ENGINES = ("postgres", "mysql", "valkey")

    def check_migration(
        self,
        name: str,
        source_service_uri: str,
        *,
        method: str | None = None,
        ignore_dbs: str | None = None,
        zone: str | None = None,
        wait: bool | None = None,
    ) -> dict:
        """Start a migration pre-check (``POST /dbaas-task-migration-check/{name}``).

        ``source_service_uri`` is the source database's URI **with admin
        credentials** — read it from a secret store, never a literal.
        ``method`` is ``"dump"`` or ``"replication"``; ``ignore_dbs`` is a
        comma-separated list (mysql only). Returns the settled operation
        envelope; its ``reference.id`` is the task to read with
        :meth:`get_task`.

        .. warning::
           Implemented from the API reference — pending live verification.
        """
        body: dict[str, Any] = {"source-service-uri": source_service_uri}
        if method is not None:
            body["method"] = method
        if ignore_dbs is not None:
            body["ignore-dbs"] = ignore_dbs
        zone = self._zone(zone)
        response = self.client.post(f"dbaas-task-migration-check/{name}", zone=zone, json=body)
        return self._settle(response, zone=zone, wait=wait)

    def get_task(self, name: str, task_id: str, *, zone: str | None = None) -> DBaaSTask:
        """Read a DBaaS background task (``GET /dbaas-task/{name}/{id}``).

        Covers the migration check and the pg upgrade check.
        """
        payload = self.client.get(f"dbaas-task/{name}/{task_id}", zone=self._zone(zone))
        return DBaaSTask.model_validate(payload)

    def get_migration_status(self, name: str, *, zone: str | None = None) -> DBaaSMigrationStatus:
        """Return the service's migration status (``GET /dbaas-migration-status/{name}``)."""
        payload = self.client.get(f"dbaas-migration-status/{name}", zone=self._zone(zone))
        return DBaaSMigrationStatus.model_validate(payload)

    def stop_migration(
        self,
        name: str,
        *,
        service_type: str,
        zone: str | None = None,
        wait: bool | None = None,
    ) -> dict:
        """Stop a running migration (``POST dbaas-{type}/{name}/migration/stop``).

        Available for pg, mysql and valkey; other engines raise ``ValueError``.
        """
        url_type = self._url_type(service_type)
        if url_type not in self._MIGRATION_ENGINES:
            raise ValueError(
                f"service type {service_type!r} has no migration; only pg, mysql and valkey do"
            )
        zone = self._zone(zone)
        response = self.client.post(f"dbaas-{url_type}/{name}/migration/stop", zone=zone)
        return self._settle(response, zone=zone, wait=wait)

    # ------------------------------------------------------------------ #
    # PostgreSQL: connection pools, replication privilege, upgrade check
    # ------------------------------------------------------------------ #

    def create_connection_pool(
        self,
        name: str,
        pool_name: str,
        database_name: str,
        *,
        mode: str | None = None,
        size: int | None = None,
        username: str | None = None,
        zone: str | None = None,
        wait: bool | None = None,
    ) -> dict:
        """Create a PgBouncer connection pool (``POST dbaas-postgres/{name}/connection-pool``).

        ``mode`` is ``"transaction"``, ``"statement"`` or ``"session"``;
        ``size`` is 1–10000; ``username`` is the pool's database user. List
        existing pools via :attr:`DBaaSService.connection_pools` on
        :meth:`get_connection_info`.
        """
        body: dict[str, Any] = {"name": pool_name, "database-name": database_name}
        if mode is not None:
            body["mode"] = mode
        if size is not None:
            body["size"] = size
        if username is not None:
            body["username"] = username
        zone = self._zone(zone)
        response = self.client.post(f"dbaas-postgres/{name}/connection-pool", zone=zone, json=body)
        return self._settle(response, zone=zone, wait=wait)

    def update_connection_pool(
        self,
        name: str,
        pool_name: str,
        *,
        database_name: str | None = None,
        mode: str | None = None,
        size: int | None = None,
        username: str | None = None,
        zone: str | None = None,
        wait: bool | None = None,
    ) -> dict:
        """Update a connection pool (``PUT dbaas-postgres/{name}/connection-pool/{pool}``).

        Only the fields you pass are sent.
        """
        body: dict[str, Any] = {}
        if database_name is not None:
            body["database-name"] = database_name
        if mode is not None:
            body["mode"] = mode
        if size is not None:
            body["size"] = size
        if username is not None:
            body["username"] = username
        zone = self._zone(zone)
        response = self.client.put(
            f"dbaas-postgres/{name}/connection-pool/{pool_name}", zone=zone, json=body
        )
        return self._settle(response, zone=zone, wait=wait)

    def delete_connection_pool(
        self, name: str, pool_name: str, *, zone: str | None = None, wait: bool | None = None
    ) -> dict:
        """Delete a connection pool (``DELETE dbaas-postgres/{name}/connection-pool/{pool}``)."""
        zone = self._zone(zone)
        response = self.client.delete(
            f"dbaas-postgres/{name}/connection-pool/{pool_name}", zone=zone
        )
        return self._settle(response, zone=zone, wait=wait)

    def set_allow_replication(
        self,
        name: str,
        username: str,
        allow: bool,
        *,
        zone: str | None = None,
        wait: bool | None = None,
    ) -> dict:
        """Grant or revoke a pg user's replication privilege.

        Wraps ``PUT dbaas-postgres/{name}/user/{username}/allow-replication``.
        The spec documents the service's user list as the response; live, it
        answers with an operation (verified 2026-11-10), awaited unless
        ``wait=False``.
        """
        zone = self._zone(zone)
        response = self.client.put(
            f"dbaas-postgres/{name}/user/{username}/allow-replication",
            zone=zone,
            json={"allow-replication": allow},
        )
        return self._settle(response, zone=zone, wait=wait)

    def check_upgrade(
        self, name: str, target_version: str, *, zone: str | None = None
    ) -> DBaaSTask:
        """Check whether a pg service can upgrade to ``target_version``.

        Wraps ``POST dbaas-postgres/{name}/upgrade-check``, which answers with
        the task directly (re-read it with :meth:`get_task` while it runs).
        Changes nothing on the service.
        """
        payload = self.client.post(
            f"dbaas-postgres/{name}/upgrade-check",
            zone=self._zone(zone),
            json={"target-version": target_version},
        )
        return DBaaSTask.model_validate(payload)

    # ------------------------------------------------------------------ #
    # MySQL
    # ------------------------------------------------------------------ #

    def enable_writes(
        self, name: str, *, zone: str | None = None, wait: bool | None = None
    ) -> dict:
        """Temporarily re-enable writes on a read-only mysql service.

        Wraps ``PUT dbaas-mysql/{name}/enable/writes``.

        MySQL services switch to read-only when their storage fills up; this
        lifts that for a short window so you can delete data or upgrade the plan.
        """
        zone = self._zone(zone)
        response = self.client.put(f"dbaas-mysql/{name}/enable/writes", zone=zone)
        return self._settle(response, zone=zone, wait=wait)

    # ------------------------------------------------------------------ #
    # Kafka: topic / schema-registry ACL entries, Kafka Connect secrets
    # ------------------------------------------------------------------ #

    def add_kafka_topic_acl(
        self,
        name: str,
        username: str,
        topic: str,
        permission: str,
        *,
        zone: str | None = None,
        wait: bool | None = None,
    ) -> dict:
        """Add a topic ACL entry (``POST dbaas-kafka/{name}/topic/acl-config``).

        ``permission`` is ``"admin"``, ``"read"``, ``"readwrite"`` or
        ``"write"``; ``topic`` and ``username`` accept wildcards. Read the
        entries (and their ids) with :meth:`get_acl_config`.
        """
        zone = self._zone(zone)
        response = self.client.post(
            f"dbaas-kafka/{name}/topic/acl-config",
            zone=zone,
            json={"username": username, "topic": topic, "permission": permission},
        )
        return self._settle(response, zone=zone, wait=wait)

    def delete_kafka_topic_acl(
        self, name: str, acl_id: str, *, zone: str | None = None, wait: bool | None = None
    ) -> dict:
        """Delete a topic ACL entry (``DELETE dbaas-kafka/{name}/topic/acl-config/{acl-id}``)."""
        zone = self._zone(zone)
        response = self.client.delete(f"dbaas-kafka/{name}/topic/acl-config/{acl_id}", zone=zone)
        return self._settle(response, zone=zone, wait=wait)

    def add_kafka_schema_registry_acl(
        self,
        name: str,
        username: str,
        resource: str,
        permission: str,
        *,
        zone: str | None = None,
        wait: bool | None = None,
    ) -> dict:
        """Add a Schema Registry ACL entry (``POST dbaas-kafka/{name}/schema-registry/acl-config``).

        ``permission`` is ``"schema_registry_read"`` or
        ``"schema_registry_write"``; ``resource`` is e.g. ``"Subject:orders-*"``.
        """
        zone = self._zone(zone)
        response = self.client.post(
            f"dbaas-kafka/{name}/schema-registry/acl-config",
            zone=zone,
            json={"username": username, "resource": resource, "permission": permission},
        )
        return self._settle(response, zone=zone, wait=wait)

    def delete_kafka_schema_registry_acl(
        self, name: str, acl_id: str, *, zone: str | None = None, wait: bool | None = None
    ) -> dict:
        """Delete a Schema Registry ACL entry (``DELETE …/schema-registry/acl-config/{acl-id}``)."""
        zone = self._zone(zone)
        response = self.client.delete(
            f"dbaas-kafka/{name}/schema-registry/acl-config/{acl_id}", zone=zone
        )
        return self._settle(response, zone=zone, wait=wait)

    def reveal_kafka_connect_password(self, name: str, *, zone: str | None = None) -> dict:
        """Return the Kafka Connect credentials.

        Wraps ``GET dbaas-kafka/{name}/connect/password/reveal``.

        .. warning::
           The returned dict holds a live password in clear text. Never log
           or print it. Needs a plan with Kafka Connect enabled: on the
           cheapest plan (no Connect) the API answers 500. Not live-verified
           on a Connect-capable plan.
        """
        return self.client.get(f"dbaas-kafka/{name}/connect/password/reveal", zone=self._zone(zone))

    # ------------------------------------------------------------------ #
    # OpenSearch ACL
    # ------------------------------------------------------------------ #

    def set_opensearch_acl_config(
        self,
        name: str,
        *,
        acl_enabled: bool | None = None,
        extended_acl_enabled: bool | None = None,
        acls: list[dict] | None = None,
        zone: str | None = None,
        wait: bool | None = None,
    ) -> dict:
        """Replace the OpenSearch ACL config (``PUT dbaas-opensearch/{name}/acl-config``).

        ``acls`` is a list of ``{"username": ..., "rules": [{"index": ...,
        "permission": ...}]}`` entries (permission ``admin`` / ``read`` /
        ``deny`` / ``readwrite`` / ``write``). Read the current config with
        :meth:`get_acl_config`.

        The live API treats this PUT as a full replace and rejects a body
        missing any of the three fields (the spec marks them optional), so an
        argument left as ``None`` keeps its current value, read first.
        """
        zone = self._zone(zone)
        if acl_enabled is None or extended_acl_enabled is None or acls is None:
            current = self.get_acl_config(name, service_type="opensearch", zone=zone)
            if acl_enabled is None:
                acl_enabled = bool(current.get("acl-enabled"))
            if extended_acl_enabled is None:
                extended_acl_enabled = bool(current.get("extended-acl-enabled"))
            if acls is None:
                acls = list(current.get("acls") or [])
        body: dict[str, Any] = {
            "acl-enabled": acl_enabled,
            "extended-acl-enabled": extended_acl_enabled,
            "acls": acls,
        }
        response = self.client.put(f"dbaas-opensearch/{name}/acl-config", zone=zone, json=body)
        return self._settle(response, zone=zone, wait=wait)

    # ------------------------------------------------------------------ #
    # Valkey users and their access control
    # ------------------------------------------------------------------ #

    def list_valkey_users(self, name: str, *, zone: str | None = None) -> list[DBaaSValkeyUser]:
        """List a Valkey service's users with their ACLs (``GET dbaas-valkey/{name}/user``)."""
        payload = self.client.get(f"dbaas-valkey/{name}/user", zone=self._zone(zone))
        users = payload.get("users") if isinstance(payload, dict) else None
        return [DBaaSValkeyUser.model_validate(u) for u in users or [] if isinstance(u, dict)]

    def update_valkey_user_access_control(
        self,
        name: str,
        username: str,
        access_control: DBaaSValkeyAccessControl | dict,
        *,
        zone: str | None = None,
        wait: bool | None = None,
    ) -> dict:
        """Replace a Valkey user's ACL (``PUT dbaas-valkey/{name}/user/{username}``)."""
        zone = self._zone(zone)
        response = self.client.put(
            f"dbaas-valkey/{name}/user/{username}",
            zone=zone,
            json={"access-control": to_api_payload(access_control)},
        )
        return self._settle(response, zone=zone, wait=wait)
