"""CLI entry point: ``exoscale-connector`` — umbrella over the per-asset tools.

Every per-asset console script remains available; this command simply
namespaces them so a single binary is enough::

    exoscale-connector instance list
    exoscale-connector security-group create --json '{"name": "web"}'
    exoscale-connector bucket list-objects --bucket backups

The first argument selects the asset; everything after it is handed verbatim
to that asset's own CLI (same flags, same exit codes). Asset modules import
lazily so startup cost stays flat as the asset list grows.
"""
from __future__ import annotations

import importlib
import sys
from typing import Optional, Sequence

from .. import __version__

# asset command -> module under exoscale_connector.cli
COMMANDS = {
    # Network
    "security-group": "security_group",
    "elastic-ip": "elastic_ip",
    "private-network": "private_network",
    "load-balancer": "load_balancer",
    "vpc": "vpc",
    # Compute
    "instance": "instance",
    "instance-pool": "instance_pool",
    "instance-type": "instance_type",
    "template": "template",
    "anti-affinity-group": "anti_affinity_group",
    "snapshot": "snapshot",
    "deploy-target": "deploy_target",
    # Storage
    "block-volume": "block_volume",
    "block-volume-snapshot": "block_volume_snapshot",
    "bucket": "object_storage",
    # IAM
    "api-key": "api_key",
    "iam-role": "iam_role",
    "iam-user": "iam_user",
    "ssh-key": "ssh_key",
    # Managed services
    "dns": "dns",
    "dbaas": "dbaas",
    "sks": "sks",
    # Platform
    "zone": "zone",
    "event": "event",
    # Tooling (not an asset type)
    "skill": "skill",
}


def _usage() -> str:
    assets = "\n".join(f"  {name}" for name in COMMANDS if name != "skill")
    return (
        "usage: exoscale-connector <asset> [args...]\n"
        "\n"
        "Manage Exoscale resources. Run 'exoscale-connector <asset> --help' for\n"
        "the asset's verbs and options.\n"
        "\n"
        f"assets:\n{assets}\n"
        "\n"
        "tooling:\n"
        "  skill        install the bundled advisor skill (see 'skill --help')\n"
    )


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args or args[0] in ("-h", "--help"):
        stream = sys.stdout if args else sys.stderr
        stream.write(_usage())
        return 0 if args else 2
    if args[0] == "--version":
        sys.stdout.write(f"exoscale-connector {__version__}\n")
        return 0

    module_name = COMMANDS.get(args[0])
    if module_name is None:
        sys.stderr.write(f"error: unknown asset {args[0]!r}\n\n{_usage()}")
        return 2
    module = importlib.import_module(f".{module_name}", __package__)
    return module.main(args[1:])


if __name__ == "__main__":
    sys.exit(main())
