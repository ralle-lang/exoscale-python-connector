"""Unit tests for the IAM expression-building helpers."""
from __future__ import annotations

from exoscale_connector import iam_expr as e


def test_quote_escapes_quotes_and_backslashes() -> None:
    assert e.quote("plain") == '"plain"'
    assert e.quote('a"b') == '"a\\"b"'
    assert e.quote("a\\b") == '"a\\\\b"'


def test_eq_and_ne() -> None:
    assert e.eq("resources.bucket", "backups") == 'resources.bucket == "backups"'
    assert e.ne("resources.bucket", "backups") == 'resources.bucket != "backups"'


def test_has() -> None:
    assert e.has("parameters", "type") == 'parameters.has("type")'


def test_operation_in_quotes_each_item() -> None:
    assert e.operation_in(["list-buckets", "get-object"]) == (
        'operation in ["list-buckets", "get-object"]'
    )


def test_operation_in_escapes_untrusted_values() -> None:
    assert e.operation_in(['evil"]']) == 'operation in ["evil\\"]"]'


def test_and_or_parenthesise() -> None:
    assert e.and_("a", "b") == "(a && b)"
    assert e.or_("a", "b", "c") == "(a || b || c)"


def test_composed_expression_reads_naturally() -> None:
    expr = e.and_(e.has("parameters", "type"), e.ne("parameters.type", "TXT"))
    assert expr == '(parameters.has("type") && parameters.type != "TXT")'
