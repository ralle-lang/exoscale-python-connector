"""Shared argparse harness for the per-asset CLIs.

Most per-asset CLIs only need to call :func:`run_resource_cli` with their
:class:`~exoscale_connector.resources._base.ResourceClient` subclass; this module
provides the common verbs (``list``/``get``/``find``/``create``/``delete``),
credential wiring from the environment, JSON I/O, and consistent error/exit codes.

CLIs that manage more than one resource kind (e.g. ``dns`` with domains and
records, ``sks`` with clusters and nodepools) pass a :class:`PrimaryResource`
and one or more :class:`SubResource` specs; the harness then emits
``<verb>-<noun>`` commands (``list-domains``, ``create-record`` …) instead of the
bare verbs. CLIs whose verbs don't fit this shape at all (e.g. ``dbaas``) build
their own parser/dispatch and reuse the public helpers here (:func:`base_parser`,
:func:`load_payload`, :func:`dump`, :func:`execute_cli`).
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from typing import Any, Callable, Optional, Sequence, Tuple, Type

from ..client import ExoscaleClient
from ..errors import ExoscaleError
from ..models import ExoscaleModel
from ..resources._base import ResourceClient

# A dispatch callback: given a constructed resource client and parsed args,
# return the JSON-serialisable result of the requested command.
Dispatch = Callable[[Any, argparse.Namespace], Any]


@dataclass(frozen=True)
class PrimaryResource:
    """Names a CLI's primary resource so base verbs read as ``<verb>-<noun>``.

    Used by multi-resource CLIs where a bare ``list`` would be ambiguous.
    ``verbs`` selects which of the base verbs to expose (``find`` is opt-in).
    """

    singular: str
    plural: str
    verbs: Sequence[str] = ("list", "get", "create", "delete")


@dataclass(frozen=True)
class SubResource:
    """A child resource exposed as ``<verb>-<singular>`` commands.

    Each verb maps to a method on the *parent* resource client, taking the parent
    id (from ``parent_arg``) first:

    * ``list``   -> ``list_method(parent_id)``
    * ``create`` -> ``create_method(parent_id, payload, wait=...)``
    * ``delete`` -> ``delete_method(parent_id, item_id, wait=...)``
    """

    singular: str
    plural: str
    parent_arg: str  # e.g. "--domain-id"
    list_method: str
    create_method: str
    delete_method: str
    verbs: Sequence[str] = ("list", "create", "delete")

    @property
    def parent_dest(self) -> str:
        """The argparse attribute name derived from ``parent_arg``."""
        return self.parent_arg.lstrip("-").replace("-", "_")


# ------------------------------------------------------------------ #
# Public building blocks (also imported by bespoke CLIs such as dbaas)
# ------------------------------------------------------------------ #

def base_parser(prog: str, description: str) -> Tuple[argparse.ArgumentParser, Any]:
    """Return a parser pre-wired with ``--zone`` plus its subparsers handle."""
    parser = argparse.ArgumentParser(prog=prog, description=description)
    parser.add_argument(
        "--zone",
        default=None,
        help="Exoscale zone (defaults to EXOSCALE_ZONE)",
    )
    sub = parser.add_subparsers(dest="command")
    return parser, sub


def add_payload_args(subparser: argparse.ArgumentParser) -> None:
    """Add the mutually-exclusive ``--json`` / ``--file`` payload source."""
    src = subparser.add_mutually_exclusive_group(required=True)
    src.add_argument("--json", help="Inline JSON payload")
    src.add_argument("--file", help="Path to a JSON payload file ('-' for stdin)")


def _add_no_wait(subparser: argparse.ArgumentParser) -> None:
    """Add the ``--no-wait`` flag shared by create/delete verbs."""
    subparser.add_argument(
        "--no-wait", action="store_true", help="Do not await the async operation"
    )


def load_payload(args: argparse.Namespace) -> dict:
    """Read a create payload from ``--json`` or ``--file`` (``-`` = stdin)."""
    if args.json is not None:
        raw = args.json
    elif args.file == "-":
        raw = sys.stdin.read()
    else:
        with open(args.file, encoding="utf-8") as handle:
            raw = handle.read()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ExoscaleError(f"invalid JSON payload: {exc}") from exc
    if not isinstance(data, dict):
        raise ExoscaleError("payload must be a JSON object")
    return data


def dump(model: Any) -> Any:
    """Serialise a model (or list/None) to plain JSON-compatible data."""
    if isinstance(model, ExoscaleModel):
        return model.model_dump(by_alias=True, exclude_none=True)
    return model


def print_json(result: Any) -> None:
    """Write ``result`` to stdout as newline-terminated JSON."""
    json.dump(result, sys.stdout, indent=2, sort_keys=False)
    sys.stdout.write("\n")


def execute_cli(
    parser: argparse.ArgumentParser,
    resource_cls: Type[ResourceClient],
    dispatch: Dispatch,
    *,
    argv: Optional[Sequence[str]] = None,
) -> int:
    """Parse ``argv``, build the client/resource, run ``dispatch``, print JSON.

    Returns a process exit code: 0 on success, 1 on a connector error (reported
    on stderr without a traceback), 2 when no command was given.
    """
    args = parser.parse_args(argv)
    if not getattr(args, "command", None):
        parser.print_help(sys.stderr)
        return 2

    try:
        client = ExoscaleClient.from_env(zone=args.zone)
        resource = resource_cls(client, zone=args.zone)
        result = dispatch(resource, args)
    except ExoscaleError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    print_json(result)
    return 0


# ------------------------------------------------------------------ #
# Generic resource CLI
# ------------------------------------------------------------------ #

def run_resource_cli(
    resource_cls: Type[ResourceClient],
    *,
    prog: str,
    description: str,
    argv: Optional[Sequence[str]] = None,
    primary: Optional[PrimaryResource] = None,
    sub_resources: Sequence[SubResource] = (),
) -> int:
    """Run a standard resource CLI for ``resource_cls``.

    With neither ``primary`` nor ``sub_resources``, exposes the bare verbs
    ``list``/``get``/``find``/``create``/``delete``. Pass ``primary`` (and
    optionally ``sub_resources``) for multi-resource CLIs that need
    ``<verb>-<noun>`` commands instead.
    """
    parser = _build_parser(prog, description, primary, sub_resources)
    return execute_cli(parser, resource_cls, _dispatch, argv=argv)


# The bare-verb default for single-resource CLIs (note: includes ``find``).
_BARE = PrimaryResource(singular="", plural="", verbs=("list", "get", "find", "create", "delete"))


def _verb_command(verb: str, singular: str, plural: str) -> str:
    """Command name for a verb: ``list`` pluralises, the rest take the singular."""
    return f"list-{plural}" if verb == "list" else f"{verb}-{singular}"


def _build_parser(
    prog: str,
    description: str,
    primary: Optional[PrimaryResource],
    sub_resources: Sequence[SubResource],
) -> argparse.ArgumentParser:
    parser, sub = base_parser(prog, description)
    bare = primary is None and not sub_resources
    _add_primary_verbs(sub, primary or _BARE, bare=bare)
    for spec in sub_resources:
        _add_sub_verbs(sub, spec)
    return parser


def _add_primary_verbs(sub: Any, primary: PrimaryResource, *, bare: bool) -> None:
    """Register the primary resource's verbs (bare or ``<verb>-<noun>``)."""
    for verb in primary.verbs:
        name = verb if bare else _verb_command(verb, primary.singular, primary.plural)
        if verb == "list":
            p = sub.add_parser(name, help="List all resources")
        elif verb == "get":
            p = sub.add_parser(name, help="Fetch one resource by id")
            p.add_argument("--id", required=True)
        elif verb == "find":
            p = sub.add_parser(name, help="Find one resource by name")
            p.add_argument("--name", required=True)
        elif verb == "create":
            p = sub.add_parser(name, help="Create a resource from a JSON payload")
            add_payload_args(p)
            _add_no_wait(p)
        elif verb == "delete":
            p = sub.add_parser(name, help="Delete a resource by id")
            p.add_argument("--id", required=True)
            _add_no_wait(p)
        else:
            raise ValueError(f"unknown primary verb: {verb}")
        p.set_defaults(_target="primary", _verb=verb)


def _add_sub_verbs(sub: Any, spec: SubResource) -> None:
    """Register a sub-resource's ``<verb>-<singular>`` commands."""
    for verb in spec.verbs:
        if verb == "list":
            p = sub.add_parser(f"list-{spec.plural}", help=f"List {spec.plural} for a parent")
            p.add_argument(spec.parent_arg, required=True)
        elif verb == "create":
            p = sub.add_parser(f"create-{spec.singular}", help=f"Create a {spec.singular}")
            p.add_argument(spec.parent_arg, required=True)
            add_payload_args(p)
            _add_no_wait(p)
        elif verb == "delete":
            p = sub.add_parser(f"delete-{spec.singular}", help=f"Delete a {spec.singular} by id")
            p.add_argument(spec.parent_arg, required=True)
            p.add_argument("--id", required=True)
            _add_no_wait(p)
        else:
            raise ValueError(f"unknown sub-resource verb: {verb}")
        p.set_defaults(_target="sub", _verb=verb, _sub=spec)


def _dispatch(resource: ResourceClient, args: argparse.Namespace) -> Any:
    """Route a parsed command (tagged via ``set_defaults``) to a client method."""
    verb = args._verb
    if args._target == "primary":
        if verb == "list":
            return [dump(item) for item in resource.list()]
        if verb == "get":
            return dump(resource.get(args.id))
        if verb == "find":
            found = resource.find_by_name(args.name)
            return dump(found) if found is not None else None
        if verb == "create":
            return dump(resource.create(load_payload(args), wait=not args.no_wait))
        if verb == "delete":
            return dump(resource.delete(args.id, wait=not args.no_wait))
    else:
        spec: SubResource = args._sub
        parent_id = getattr(args, spec.parent_dest)
        if verb == "list":
            return [dump(item) for item in getattr(resource, spec.list_method)(parent_id)]
        if verb == "create":
            return dump(
                getattr(resource, spec.create_method)(
                    parent_id, load_payload(args), wait=not args.no_wait
                )
            )
        if verb == "delete":
            return dump(
                getattr(resource, spec.delete_method)(parent_id, args.id, wait=not args.no_wait)
            )
    raise ExoscaleError(f"unknown command: {args.command}")
