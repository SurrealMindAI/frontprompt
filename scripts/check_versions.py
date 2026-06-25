#!/usr/bin/env python3
"""Verify every version string in the repo is identical.

frontprompt is released as ONE version across seven places: the Python package,
the CLI ``__version__``, both Claude Code ``plugin.json`` bundles, the
``marketplace.json`` entry, the pinned ``uvx`` launch in ``plugin/.mcp.json``,
and the marketing/docs ``site/package.json``. If they drift, a plugin update in
Claude Code stops mapping cleanly to a PyPI release (and the published site
stops matching the shipped tool). This script asserts they all match.

Run by:
  - the ``pre-push`` git hook (``.githooks/pre-push``) — blocks drift before push,
    and on a ``vX.Y.Z`` tag push also asserts the tag matches;
  - CI (``ci.yml`` quality job);
  - the release workflow (``release.yml``) with ``--tag`` so a tag can only ship
    if every version already equals it.

Usage::

    python scripts/check_versions.py                 # all internal versions equal?
    python scripts/check_versions.py --tag v1.2.3     # ...and equal to the tag?

Stdlib only (tomllib is 3.11+), so it runs with a bare ``python3``.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _pyproject() -> str:
    data = tomllib.loads((ROOT / "pyproject.toml").read_text("utf-8"))
    return str(data["project"]["version"])


def _init() -> str:
    text = (ROOT / "src/frontprompt/__init__.py").read_text("utf-8")
    match = re.search(r'^__version__\s*=\s*"([^"]+)"', text, re.MULTILINE)
    if not match:
        raise ValueError("__version__ not found in src/frontprompt/__init__.py")
    return match.group(1)


def _json_field(rel_path: str, *keys: str) -> str:
    data: object = json.loads((ROOT / rel_path).read_text("utf-8"))
    for key in keys:
        assert isinstance(data, (dict, list))
        data = data[key] if isinstance(data, dict) else data[int(key)]
    return str(data)


def _mcp_pin() -> str:
    data = json.loads((ROOT / "plugin/.mcp.json").read_text("utf-8"))
    args = data["mcpServers"]["frontprompt"]["args"]
    for arg in args:
        match = re.fullmatch(r"frontprompt==(\S+)", str(arg))
        if match:
            return match.group(1)
    raise ValueError("no `frontprompt==<version>` pin found in plugin/.mcp.json args")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tag", default=None, help="also require this git tag (vX.Y.Z) to match")
    args = parser.parse_args()

    sources: dict[str, str] = {
        "pyproject.toml": _pyproject(),
        "src/frontprompt/__init__.py": _init(),
        ".claude-plugin/plugin.json": _json_field(".claude-plugin/plugin.json", "version"),
        "plugin/.claude-plugin/plugin.json": _json_field("plugin/.claude-plugin/plugin.json", "version"),
        ".claude-plugin/marketplace.json": _json_field(".claude-plugin/marketplace.json", "plugins", "0", "version"),
        "plugin/.mcp.json (uvx pin)": _mcp_pin(),
        "site/package.json": _json_field("site/package.json", "version"),
    }
    if args.tag is not None:
        sources["git tag"] = args.tag.lstrip("v")

    width = max(len(name) for name in sources)
    for name, version in sources.items():
        print(f"  {name:<{width}}  {version}")

    distinct = set(sources.values())
    if len(distinct) == 1:
        print(f"\nOK — all versions match: {distinct.pop()}")
        return 0

    print(f"\nFAIL — {len(distinct)} distinct versions found: {sorted(distinct)}", file=sys.stderr)
    print("Bump every source above to the same version before tagging/releasing.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
