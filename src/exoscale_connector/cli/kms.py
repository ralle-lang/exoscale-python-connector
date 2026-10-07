"""CLI entry point: ``exoscale-kms``.

Manages Exoscale KMS keys via the APIv2. KMS doesn't fit the generic resource
harness — it has no immediate ``delete`` (deletion is scheduled), and a set of
sub-action verbs (enable/disable, rotation, deletion lifecycle, replication) —
so this CLI builds its own parser and dispatch, reusing the shared plumbing
(:func:`base_parser`, :func:`dump`, :func:`execute_cli`).

The crypto operations (encrypt / decrypt / re-encrypt / generate-data-key) are
**intentionally not exposed here**: they take and return secret material, and
CLI arguments leak into the process list. Use
:class:`~exoscale_connector.resources.kms.KmsKeyClient` from Python for those.
"""

from __future__ import annotations

import sys
from typing import Any, Optional, Sequence

from ..errors import ExoscaleError
from ..resources.kms import KmsKeyClient
from ._base import add_payload_args, base_parser, dump, execute_cli, load_payload


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Entry point for the ``exoscale-kms`` binary."""
    return execute_cli(_build_parser(), KmsKeyClient, _dispatch, argv=argv)


def _build_parser() -> Any:
    parser, sub = base_parser("exoscale-kms", "Manage Exoscale KMS keys via the APIv2.")

    sub.add_parser("list", help="List all KMS keys")

    p_get = sub.add_parser("get", help="Fetch one key by id")
    p_get.add_argument("--id", required=True)

    p_create = sub.add_parser("create", help="Create a KMS key from a JSON payload")
    add_payload_args(p_create, required=False)

    # Single-id sub-actions: verb -> (command name, help).
    for name, helptext in (
        ("enable", "Enable a key"),
        ("disable", "Disable a key"),
        ("rotate", "Rotate the key material now"),
        ("disable-rotation", "Disable automatic rotation"),
        ("list-rotations", "List a key's past rotations"),
        ("cancel-deletion", "Cancel a scheduled deletion"),
    ):
        p = sub.add_parser(name, help=helptext)
        p.add_argument("--id", required=True)

    p_enrot = sub.add_parser("enable-rotation", help="Enable automatic rotation")
    p_enrot.add_argument("--id", required=True)
    p_enrot.add_argument("--period", type=int, default=None, help="Rotation period in days")

    p_sched = sub.add_parser("schedule-deletion", help="Schedule a key for deletion")
    p_sched.add_argument("--id", required=True)
    p_sched.add_argument("--delay-days", type=int, default=None, help="Waiting period in days")

    p_rep = sub.add_parser("replicate", help="Replicate a multi-zone key into another zone")
    p_rep.add_argument("--id", required=True)
    p_rep.add_argument("--to-zone", required=True, help="Destination zone")

    return parser


def _dispatch(kms: KmsKeyClient, args: Any) -> Any:
    """Route a parsed sub-command to the matching client method."""
    cmd = args.command
    if cmd == "list":
        return [dump(k) for k in kms.list()]
    if cmd == "get":
        return dump(kms.get(args.id))
    if cmd == "create":
        return dump(kms.create(load_payload(args)))
    if cmd == "enable":
        return kms.enable(args.id)
    if cmd == "disable":
        return kms.disable(args.id)
    if cmd == "rotate":
        return kms.rotate(args.id)
    if cmd == "enable-rotation":
        return kms.enable_rotation(args.id, rotation_period=args.period)
    if cmd == "disable-rotation":
        return kms.disable_rotation(args.id)
    if cmd == "list-rotations":
        return kms.list_rotations(args.id)
    if cmd == "schedule-deletion":
        return kms.schedule_deletion(args.id, delay_days=args.delay_days)
    if cmd == "cancel-deletion":
        return kms.cancel_deletion(args.id)
    if cmd == "replicate":
        return kms.replicate(args.id, args.to_zone)
    raise ExoscaleError(f"unknown command: {cmd}")


if __name__ == "__main__":
    sys.exit(main())
