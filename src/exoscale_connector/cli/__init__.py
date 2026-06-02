"""Thin command-line front-ends for the resource clients.

Each asset type gets a small module here that delegates to :func:`run_resource_cli`
in :mod:`exoscale_connector.cli._base`, and is wired to a console script in
``pyproject.toml`` (e.g. ``exoscale-security-group``). The CLIs are intentionally
thin: all behaviour lives in the resource clients so library and CLI never diverge.
"""
