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
    exoscale-bucket list-objects --bucket my-bucket --prefix logs/
    exoscale-bucket upload --bucket my-bucket --key a.txt --file ./a.txt
    exoscale-bucket download --bucket my-bucket --key a.txt --file ./a.txt
    exoscale-bucket delete-object --bucket my-bucket --key a.txt
    exoscale-bucket presign --bucket my-bucket --key a.txt --method get

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
from ._base import dump, print_result


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

    print_result(result, args.output)
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
    parser.add_argument(
        "--output",
        choices=("json", "table"),
        default="json",
        help="Output format (default: json)",
    )
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("list", help="List all buckets")

    p_create = sub.add_parser("create", help="Create a bucket")
    p_create.add_argument("--name", required=True, help="Bucket name")

    p_delete = sub.add_parser("delete", help="Delete a bucket")
    p_delete.add_argument("--name", required=True, help="Bucket name")

    p_exists = sub.add_parser("exists", help="Check whether a bucket exists")
    p_exists.add_argument("--name", required=True, help="Bucket name")

    p_lo = sub.add_parser("list-objects", help="List objects in a bucket")
    p_lo.add_argument("--bucket", required=True)
    p_lo.add_argument("--prefix", default=None, help="Only keys starting with this prefix")
    p_lo.add_argument("--limit", type=int, default=None, help="Stop after N objects")

    p_up = sub.add_parser("upload", help="Upload a local file to a bucket")
    p_up.add_argument("--bucket", required=True)
    p_up.add_argument("--key", required=True)
    p_up.add_argument("--file", required=True, help="Local file path")

    p_down = sub.add_parser("download", help="Download an object to a local file")
    p_down.add_argument("--bucket", required=True)
    p_down.add_argument("--key", required=True)
    p_down.add_argument("--file", required=True, help="Local destination path")

    p_del = sub.add_parser("delete-object", help="Delete one object")
    p_del.add_argument("--bucket", required=True)
    p_del.add_argument("--key", required=True)

    p_sign = sub.add_parser("presign", help="Generate a presigned URL (treat the URL as a secret)")
    p_sign.add_argument("--bucket", required=True)
    p_sign.add_argument("--key", required=True)
    p_sign.add_argument("--method", choices=("get", "put"), default="get")
    p_sign.add_argument("--expires", type=int, default=3600, help="Validity in seconds")

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
    if args.command == "list-objects":
        objects = client.list_objects(args.bucket, prefix=args.prefix, limit=args.limit)
        return [dump(o) for o in objects]
    if args.command == "upload":
        client.upload_file(args.bucket, args.key, args.file)
        return {"bucket": args.bucket, "key": args.key, "uploaded": True}
    if args.command == "download":
        client.download_file(args.bucket, args.key, args.file)
        return {"bucket": args.bucket, "key": args.key, "downloaded": True}
    if args.command == "delete-object":
        client.delete_object(args.bucket, args.key)
        return {"bucket": args.bucket, "key": args.key, "deleted": True}
    if args.command == "presign":
        sign = client.presign_get if args.method == "get" else client.presign_put
        url = sign(args.bucket, args.key, expires_in=args.expires)
        return {"bucket": args.bucket, "key": args.key, "method": args.method, "url": url}
    raise ExoscaleError(f"unknown command: {args.command}")


if __name__ == "__main__":
    sys.exit(main())
