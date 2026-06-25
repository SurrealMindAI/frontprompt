#!/usr/bin/env bash
# Install the repo's git hooks by pointing core.hooksPath at the tracked
# .githooks/ directory. The pre-push hook enforces version consistency
# (see scripts/check_versions.py).
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
chmod +x "$ROOT/.githooks/pre-push"
git -C "$ROOT" config core.hooksPath .githooks

echo "✔ git hooks installed (core.hooksPath = .githooks)."
echo "  pre-push now runs scripts/check_versions.py and blocks version drift."
