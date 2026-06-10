"""CLI entry point: ``exoscale-bucket``.

Manage Exoscale Object Storage (SOS) buckets via the S3-compatible API.

Credentials are taken from the environment (``EXOSCALE_API_KEY`` /
``EXOSCALE_API_SECRET`` / ``EXOSCALE_ZONE``) via
:meth:`~exoscale_connector.config.ClientConfig.from_env`.

Usage examples::

    exoscale-bucket --zone de-fra-1 list
    exoscale-bucket create --name my-bucket
    exoscale-bucket delete --name my-bucket
    exoscale-bucket exists --name my-bucket

Exit codes
----------
0 — success
1 — error (message printed to stderr)
2 — bad arguments / missing subcommand
"""
from __future__ import annotations

import argparse
import sys
from typing import Optional, Sequence

from ..config import ClientConfig
from ..errors import ExoscaleError
from ..resources.object_storage import BucketClient
from ._base import dump, print_json


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Parse arguments, run the verb, print JSON. Returns an exit code."""
    parser = _build_parser()
    args = parser.parse_args(argv)

    if not getattr(args, "command", None):
        parser.print_help(sys.stderr)
        return 2

    try:
        config = ClientConfig.from_env(zone=args.zone)
        bucket_client = BucketClient(config, zone=args.zone)
        result = _dispatch(bucket_client, args)
    except ExoscaleError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    print_json(result)
    return 0


# ------------------------------------------------------------------ #
# Argument parser
# ------------------------------------------------------------------ #

def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="exoscale-bucket",
        description="Manage Exoscale Object Storage (SOS) buckets.",
    )
    parser.add_argument(
        "--zone",
        default=None,
        help="Exoscale zone (defaults to EXOSCALE_ZONE)",
    )
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("list", help="List all buckets")

    p_create = sub.add_parser("create", help="Create a bucket")
    p_create.add_argument("--name", required=True, help="Bucket name")

    p_delete = sub.add_parser("delete", help="Delete a bucket")
    p_delete.add_argument("--name", required=True, help="Bucket name")

    p_exists = sub.add_parser("exists", help="Check whether a bucket exists")
    p_exists.add_argument("--name", required=True, help="Bucket name")

    return parser


# ------------------------------------------------------------------ #
# Dispatch
# ------------------------------------------------------------------ #

def _dispatch(client: BucketClient, args: argparse.Namespace) -> object:
    """Route a parsed command to the matching BucketClient method."""
    if args.command == "list":
        return [dump(b) for b in client.list()]
    if args.command == "create":
        client.create(args.name)
        return {"name": args.name, "created": True}
    if args.command == "delete":
        client.delete(args.name)
        return {"name": args.name, "deleted": True}
    if args.command == "exists":
        found = client.exists(args.name)
        return {"name": args.name, "exists": found}
    raise ExoscaleError(f"unknown command: {args.command}")


if __name__ == "__main__":
    sys.exit(main())
