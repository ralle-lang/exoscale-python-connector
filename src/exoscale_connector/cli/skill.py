"""``exoscale-connector skill`` — install the bundled advisor skill.

The package ships an agent skill (``SKILL.md`` + ``reference.md``, generated
from the code and the live-verified docs) that AI-assisted editors discover
from a ``.claude/skills/`` directory. ``install`` copies it into the current
project (default) or the user-level skills directory::

    exoscale-connector skill install            # ./.claude/skills/exoscale-connector/
    exoscale-connector skill install --user     # ~/.claude/skills/exoscale-connector/
    exoscale-connector skill install --dest DIR # custom target directory
    exoscale-connector skill path               # print the packaged skill source

The copied files are owned by this tool: re-running ``install`` after a
package upgrade refreshes them in place.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import List, Optional, Sequence

SKILL_FILES = ("SKILL.md", "reference.md")
SKILL_NAME = "exoscale-connector"


def packaged_skill_dir() -> Path:
    """Location of the skill files shipped inside the installed package."""
    return Path(__file__).resolve().parent.parent / "_skill"


def install(dest: Path) -> List[Path]:
    """Copy the packaged skill files into ``dest``; return the written paths."""
    source = packaged_skill_dir()
    missing = [name for name in SKILL_FILES if not (source / name).exists()]
    if missing:
        raise FileNotFoundError(
            f"packaged skill is incomplete (missing {', '.join(missing)} in {source})"
        )
    dest.mkdir(parents=True, exist_ok=True)
    written = []
    for name in SKILL_FILES:
        target = dest / name
        target.write_text((source / name).read_text(encoding="utf-8"), encoding="utf-8")
        written.append(target)
    return written


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="exoscale-connector skill",
        description="Install the bundled advisor skill for AI-assisted editors.",
    )
    sub = parser.add_subparsers(dest="verb", required=True)

    p_install = sub.add_parser("install", help="copy the skill into a skills directory")
    target = p_install.add_mutually_exclusive_group()
    target.add_argument(
        "--user",
        action="store_true",
        help="install to ~/.claude/skills/ instead of the current project",
    )
    target.add_argument(
        "--dest",
        type=Path,
        help="install into this exact directory (created if absent)",
    )
    sub.add_parser("path", help="print the packaged skill source directory")

    args = parser.parse_args(argv)

    if args.verb == "path":
        print(packaged_skill_dir())
        return 0

    if args.dest is not None:
        dest = args.dest
    elif args.user:
        dest = Path.home() / ".claude" / "skills" / SKILL_NAME
    else:
        dest = Path.cwd() / ".claude" / "skills" / SKILL_NAME
    try:
        written = install(dest)
    except (OSError, FileNotFoundError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    for path in written:
        print(f"installed {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
