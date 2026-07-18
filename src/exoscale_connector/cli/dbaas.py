"""CLI entry point: ``exoscale-dbaas``.

Manages Exoscale DBaaS (managed database) services via the APIv2.

DBaaS doesn't fit the generic resource harness: services are identified by
**name** (name == id), and ``create`` uses a service-type-specific endpoint with
``--type`` / ``--name`` rather than a generic JSON payload. This CLI therefore
builds its own parser and dispatch, but reuses the shared plumbing
(:func:`base_parser`, :func:`dump`, :func:`execute_cli`) so there is no
duplicated credential/JSON/error handling.
"""

from __future__ import annotations

import json
import sys
from typing import Any, Optional, Sequence

from ..errors import ExoscaleError
from ..resources.dbaas import DBaaSServiceClient
from ._base import base_parser, dump, execute_cli


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Entry point for the ``exoscale-dbaas`` binary."""
    return execute_cli(_build_parser(), DBaaSServiceClient, _dispatch, argv=argv)


def _build_parser() -> Any:
    parser, sub = base_parser(
        "exoscale-dbaas",
        "Manage Exoscale DBaaS (managed database) services via the APIv2.",
    )

    sub.add_parser("list", help="List all managed database services")

    p_get = sub.add_parser("get", help="Fetch one service by name")
    p_get.add_argument("--name", required=True, help="Service name")

    p_create = sub.add_parser(
        "create",
        help="Create a managed database service (type-specific endpoint)",
    )
    p_create.add_argument(
        "--type",
        required=True,
        dest="service_type",
        metavar="TYPE",
        help="Service type: pg, mysql, redis, valkey, opensearch, kafka, grafana, …",
    )
    p_create.add_argument(
        "--name",
        required=True,
        help="Service name (encoded in the URL path, not the payload)",
    )
    p_create.add_argument(
        "--json",
        default=None,
        dest="json_payload",
        metavar="JSON",
        help="Inline JSON body with type-specific settings (optional)",
    )

    p_delete = sub.add_parser("delete", help="Delete a service by name")
    p_delete.add_argument("--name", required=True, help="Service name")

    return parser


def _dispatch(dbaas: DBaaSServiceClient, args: Any) -> Any:
    """Route a parsed sub-command to the matching client method."""
    if args.command == "list":
        return [dump(svc) for svc in dbaas.list()]
    if args.command == "get":
        return dump(dbaas.get(args.name))
    if args.command == "create":
        payload = _parse_optional_json(getattr(args, "json_payload", None))
        return dump(dbaas.create(payload, service_type=args.service_type, name=args.name))
    if args.command == "delete":
        return dump(dbaas.delete(args.name))
    raise ExoscaleError(f"unknown command: {args.command}")


def _parse_optional_json(raw: Optional[str]) -> dict:
    """Parse an optional inline JSON body; empty/absent means a body-less POST."""
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ExoscaleError(f"invalid JSON payload: {exc}") from exc
    if not isinstance(data, dict):
        raise ExoscaleError("payload must be a JSON object")
    return data


if __name__ == "__main__":
    sys.exit(main())
