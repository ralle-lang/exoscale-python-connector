"""Helpers for safely building Exoscale IAM policy rule *expressions*.

The expression language is Exoscale's own (a CEL-like DSL); the connector never
parses it. These helpers only take the error-prone part off your hands — quoting
and escaping a user-supplied value into a string literal — plus a few common
predicates. Each returns a plain string suitable for
:meth:`IAMPolicyRule.allow` / :meth:`IAMPolicyRule.deny`.

They do **not** validate the full grammar; anything Exoscale accepts is valid.
See the IAM policy cookbook and Exoscale's policy guide for the language itself.

Example::

    from exoscale_connector import iam_expr as e
    from exoscale_connector.resources.iam_role import IAMPolicyRule

    IAMPolicyRule.deny(e.ne("resources.bucket", user_input))
    IAMPolicyRule.allow(e.operation_in(["list-buckets", "get-object"]))
"""

from __future__ import annotations

import re
from typing import Iterable

# Field/container names are developer-written constants like "resources.bucket".
# They are interpolated into the expression verbatim, so they must never carry
# untrusted input — enforce a conservative dotted-identifier shape to fail loudly
# if one ever does.
_FIELD_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)*\Z")


def _check_field(field: str) -> str:
    """Validate a field/container name; raise ``ValueError`` on anything unsafe."""
    if not _FIELD_RE.match(field):
        raise ValueError(
            f"invalid IAM expression field name: {field!r} "
            "(expected a dotted identifier like 'resources.bucket')"
        )
    return field


def quote(value: str) -> str:
    """Return ``value`` as a double-quoted, escaped expression string literal.

    Escapes backslashes and double quotes so an arbitrary value (e.g. a bucket
    or domain name) can't break out of the literal or alter the expression.
    """
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def eq(field: str, value: str) -> str:
    """``<field> == "<value>"`` with ``value`` safely quoted."""
    return f"{_check_field(field)} == {quote(value)}"


def ne(field: str, value: str) -> str:
    """``<field> != "<value>"`` with ``value`` safely quoted."""
    return f"{_check_field(field)} != {quote(value)}"


def has(container: str, key: str) -> str:
    """``<container>.has("<key>")`` — test for an optional field's presence."""
    return f"{_check_field(container)}.has({quote(key)})"


def operation_in(operations: Iterable[str]) -> str:
    """``operation in ["a", "b", ...]`` with each operation safely quoted."""
    items = ", ".join(quote(op) for op in operations)
    return f"operation in [{items}]"


def and_(*expressions: str) -> str:
    """Combine expressions with ``&&``, parenthesised for safe nesting."""
    return "(" + " && ".join(expressions) + ")"


def or_(*expressions: str) -> str:
    """Combine expressions with ``||``, parenthesised for safe nesting."""
    return "(" + " || ".join(expressions) + ")"
