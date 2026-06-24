#!/bin/bash
# frontprompt setup — idempotent installer.
#
# Modes:
#   bash setup.sh             default: full install (uv sync + chromium + frontend
#                             overlay build + sentinel-write + plugin register)
#   bash setup.sh --check     silent health-check, exit 0 if OK, non-zero if broken
#   bash setup.sh --doctor    verbose health report
#   bash setup.sh --uninstall remove venv and ~/.frontprompt sentinel
#
# Sentinel: ~/.frontprompt/install.path records this clone's absolute path so
# the plugin-cache-installed `run-mcp.sh` can transparently redirect into the
# real clone.
set -e
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BUN_BIN="$HOME/.bun/bin"

# ── shared checks ─────────────────────────────────────
check_uv()   { command -v uv &>/dev/null; }

# bun is a build-time prereq (vite + codegen-driven overlay bundle). It is NOT
# needed to *run* the daemon — only to (re)build frontend/dist. Probe both PATH
# and bun's default install dir, since a fresh `bun install`-script run drops it
# at ~/.bun/bin without touching the current shell's PATH.
check_bun()  { command -v bun &>/dev/null || [ -x "$BUN_BIN/bun" ]; }

# A bare `[ -d .venv ]` is not enough: uv leaves dangling *.dist-info entries
# when it racy-uninstalls a package, so the directory is "present" but
# `import frontprompt` still fails. We probe the critical imports the daemon
# actually needs.
check_deps() {
  [ -d "$DIR/.venv" ] && [ -f "$DIR/uv.lock" ] || return 1
  "$DIR/.venv/bin/python" -c "import frontprompt, anyio, click, mcp, playwright, pydantic" >/dev/null 2>&1
}

check_server() { uv run --directory "$DIR" python -c "from frontprompt.cli import main" &>/dev/null; }

# Playwright ships its chromium build into a per-platform browser cache, NOT the
# .venv — so `check_deps` can't see it. Probe the cache dir directly. Honors an
# explicit PLAYWRIGHT_BROWSERS_PATH, else the OS defaults (macOS / Linux).
check_chromium() {
  local p
  for p in "${PLAYWRIGHT_BROWSERS_PATH:-}" \
           "$HOME/Library/Caches/ms-playwright" \
           "$HOME/.cache/ms-playwright"; do
    [ -n "$p" ] && compgen -G "$p/chromium-*" >/dev/null 2>&1 && return 0
  done
  return 1
}

check_frontend_deps() { [ -d "$DIR/frontend/node_modules" ]; }

# The overlay bundle is gitignored — it must be built locally. The
# daemon/show path hard-fails without it. Both the IIFE bundle and its manifest
# must be present.
check_overlay_bundle() {
  [ -f "$DIR/frontend/dist/overlay.iife.js" ] && [ -f "$DIR/frontend/dist/build-manifest.json" ]
}

get_pyproject_version() {
  awk -F'"' '/^version = "/ { print $2; exit }' "$DIR/pyproject.toml" 2>/dev/null
}

# ── modes ──────────────────────────────────────────────

mode_check() {
  check_uv && check_deps && check_chromium && check_overlay_bundle || exit 1
}

mode_doctor() {
  local ok="\033[32m[ok]\033[0m" fail="\033[31m[!!]\033[0m"
  echo "frontprompt doctor"
  check_uv   && echo -e "  $ok uv .............. $(uv --version 2>/dev/null)" \
             || echo -e "  $fail uv .............. not found"
  check_deps && echo -e "  $ok python deps ..... synced (frontprompt $(get_pyproject_version))" \
             || echo -e "  $fail python deps ..... not synced"
  check_server && echo -e "  $ok cli import ..... ok" \
                || echo -e "  $fail cli import ..... failed"
  check_chromium && echo -e "  $ok chromium ....... installed" \
                 || echo -e "  $fail chromium ....... missing (run setup.sh to install)"
  check_bun  && echo -e "  $ok bun ............. $(PATH="$BUN_BIN:$PATH" bun --version 2>/dev/null)" \
             || echo -e "  $fail bun ............. not found"
  check_frontend_deps && echo -e "  $ok frontend deps ... installed" \
                      || echo -e "  $fail frontend deps ... missing (run setup.sh)"
  check_overlay_bundle && echo -e "  $ok overlay bundle .. built" \
                       || echo -e "  $fail overlay bundle .. missing (run setup.sh to build)"
  if [ -f "$HOME/.frontprompt/install.path" ]; then
    echo -e "  $ok sentinel ........ $(<"$HOME/.frontprompt/install.path")"
  else
    echo -e "  $fail sentinel ........ missing (~/.frontprompt/install.path)"
  fi
}

mode_uninstall() {
  echo ""
  echo "  frontprompt — uninstall"
  echo "  ─────────────────────────"
  echo ""

  if command -v claude &>/dev/null; then
    echo "  [..] removing plugin registration..."
    claude plugin uninstall frontprompt 2>/dev/null || true
    claude plugin marketplace remove frontprompt 2>/dev/null || true
    echo "  [ok] plugin registration removed"
  fi

  if [ -d "$DIR/.venv" ]; then
    echo "  [..] removing .venv..."
    rm -rf "$DIR/.venv"
    echo "  [ok] .venv removed"
  else
    echo "  [--] .venv not found"
  fi

  if [ -d "$HOME/.frontprompt" ]; then
    echo "  [..] removing ~/.frontprompt..."
    rm -rf "$HOME/.frontprompt"
    echo "  [ok] ~/.frontprompt removed"
  else
    echo "  [--] ~/.frontprompt not found"
  fi

  echo ""
  echo "  uninstall complete. you can delete this directory to fully remove."
}

mode_install() {
  echo ""
  echo "  frontprompt — setup"
  echo "  ─────────────────────"
  echo ""

  # install-path sentinel — record this clone's absolute path so the
  # cache-installed `run-mcp.sh` shim can redirect MCP invocations here
  # instead of trying to self-heal from an incomplete cache copy.
  mkdir -p "$HOME/.frontprompt"
  echo "$DIR" > "$HOME/.frontprompt/install.path"
  echo "  [ok] install path .... $DIR (sentinel written)"

  if check_uv; then
    echo "  [ok] uv .............. $(uv --version 2>/dev/null)"
  else
    echo "  [..] uv .............. installing..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"
    echo "  [ok] uv .............. $(uv --version 2>/dev/null)"
  fi

  if check_deps; then
    echo "  [ok] python deps ..... synced"
  else
    echo "  [..] python deps ..... syncing..."
    # Always strip a leaked VIRTUAL_ENV (claude-hook-tap class of bug);
    # otherwise uv targets a cached environment outside .venv.
    env -u VIRTUAL_ENV uv sync --directory "$DIR"
    if ! check_deps; then
      echo "  [..] python deps ..... half-installed venv detected; reinstalling core deps"
      env -u VIRTUAL_ENV uv sync --directory "$DIR" --reinstall
    fi
    echo "  [ok] python deps ..... synced"
  fi

  if check_server; then
    echo "  [ok] cli import ...... ok"
  else
    echo "  [!!] cli import ...... verification failed (see logs)"
  fi

  if check_chromium; then
    echo "  [ok] chromium ........ installed"
  else
    echo "  [..] chromium ........ installing playwright browser..."
    env -u VIRTUAL_ENV uv run --directory "$DIR" python -m playwright install chromium
    if check_chromium; then
      echo "  [ok] chromium ........ installed"
    else
      echo "  [!!] chromium ........ install reported success but cache not found (see logs)"
    fi
  fi

  # ── frontend overlay bundle (canonical build) ──
  # bun → frontend deps → `python -m frontprompt.build` (codegen + vite). The
  # daemon/show path hard-fails without the bundle, so this is part of bootstrap.
  if check_bun; then
    echo "  [ok] bun ............. $(PATH="$BUN_BIN:$PATH" bun --version 2>/dev/null)"
  else
    echo "  [..] bun ............. installing..."
    curl -fsSL https://bun.sh/install | bash
    echo "  [ok] bun ............. $(PATH="$BUN_BIN:$PATH" bun --version 2>/dev/null)"
  fi
  # Make bun visible to this script + the vite subprocess spawned by the build.
  export PATH="$BUN_BIN:$PATH"

  if check_frontend_deps; then
    echo "  [ok] frontend deps ... installed"
  else
    echo "  [..] frontend deps ... bun install..."
    ( cd "$DIR/frontend" && bun install )
    echo "  [ok] frontend deps ... installed"
  fi

  if check_overlay_bundle; then
    echo "  [ok] overlay bundle .. built"
  else
    echo "  [..] overlay bundle .. building (codegen + vite)..."
    env -u VIRTUAL_ENV uv run --directory "$DIR" python -m frontprompt.build
    if check_overlay_bundle; then
      echo "  [ok] overlay bundle .. built"
    else
      echo "  [!!] overlay bundle .. build reported success but bundle missing (see logs)"
    fi
  fi

  if command -v claude &>/dev/null; then
    echo "  [..] registering plugin..."
    claude plugin marketplace remove frontprompt 2>/dev/null || true
    claude plugin uninstall frontprompt 2>/dev/null || true
    claude plugin marketplace add "$DIR"
    claude plugin install frontprompt
    echo "  [ok] plugin installed"
  else
    echo "  [--] claude CLI not found — register manually via:"
    echo "         /plugin marketplace add $DIR"
    echo "         /plugin install frontprompt@frontprompt"
  fi

  echo ""
  echo "  setup complete."
  true
}

# ── dispatch ───────────────────────────────────────────
case "${1:-}" in
  --check)     mode_check ;;
  --doctor)    mode_doctor ;;
  --uninstall) mode_uninstall ;;
  *)           mode_install "$@" ;;
esac
