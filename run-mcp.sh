#!/bin/bash
# frontprompt MCP-Daemon wrapper.
#
# Each invocation spawns an isolated daemon-process that owns its own private
# `frontprompt show` browser child. No daemon-singleton, no lockfile.
#
# This script is byte-identical between `<repo>/run-mcp.sh` and
# `<repo>/plugin/run-mcp.sh`. See `/Users/.../frontprompt/plugin/.mcp.json`
# for the Claude Code wiring (command = ${CLAUDE_PLUGIN_ROOT}/run-mcp.sh).
#
# Configurable via env:
#   FRONTPROMPT_MCP_START_URL  default `about:blank`; URL the spawned browser
#                              child opens with.
set -e

SOURCE="${BASH_SOURCE[0]}"
# relative-readlink bistability — macOS `readlink` returns the raw
# symlink target. For relative targets, the next iteration must resolve them
# against the symlink's own directory, not against CWD.
while [ -L "$SOURCE" ]; do
  LINK_DIR="$(cd "$(dirname "$SOURCE")" && pwd)"
  SOURCE="$(readlink "$SOURCE")"
  [[ $SOURCE != /* ]] && SOURCE="$LINK_DIR/$SOURCE"
done
DIR="$(cd "$(dirname "$SOURCE")" && pwd)"

LOG_DIR="$HOME/.frontprompt/logs"
mkdir -p "$LOG_DIR"
LOG="$LOG_DIR/run-mcp.sh.log"

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" >> "$LOG"; }

log "--- start ---"
log "BASH_SOURCE=${BASH_SOURCE[0]}"
log "DIR=$DIR"
log "PWD=$PWD"
log "CLAUDE_PLUGIN_ROOT=${CLAUDE_PLUGIN_ROOT:-<unset>}"
log "args: $*"
log "uv=$(which uv 2>/dev/null || echo '<not found>')"
log "FRONTPROMPT_MCP_START_URL=${FRONTPROMPT_MCP_START_URL:-<unset>}"

# Cache-install bridge: when Claude Code installs the plugin from the
# marketplace, it copies plugin/ into ~/.claude/plugins/cache/<name>/<plugin>/<version>/.
# That cache copy only contains run-mcp.sh + .claude-plugin/ + .mcp.json — NOT
# setup.sh, pyproject.toml, src/, .venv. So this script can't self-heal from
# the cache copy.
#
# setup.sh writes a sentinel at ~/.frontprompt/install.path recording the local
# clone's absolute path. If $DIR has no setup.sh but the sentinel points at a
# real install, re-exec into that clone's run-mcp.sh so the cache copy becomes
# a transparent shim. Users with no local clone get a clear error pointing them
# at `bash setup.sh`.
if [ ! -x "$DIR/setup.sh" ]; then
  SENTINEL="$HOME/.frontprompt/install.path"
  if [ -f "$SENTINEL" ]; then
    REAL_DIR=$(<"$SENTINEL")
    if [ -n "$REAL_DIR" ] && [ -x "$REAL_DIR/run-mcp.sh" ] && [ "$REAL_DIR" != "$DIR" ]; then
      log "cache-install: redirecting to local clone at $REAL_DIR"
      exec "$REAL_DIR/run-mcp.sh" "$@"
    fi
    log "[ERROR] sentinel at $SENTINEL points at $REAL_DIR but no run-mcp.sh there"
  else
    log "[ERROR] no setup.sh in \$DIR and no sentinel at $SENTINEL"
  fi
  echo "[ERROR] cache install missing setup.sh and no install sentinel. run: bash <frontprompt-clone>/setup.sh" >&2
  exit 1
fi

# Self-heal: if setup-check fails, attempt a re-sync. Reasons it might fail:
#   (a) fresh checkout, never installed → setup.sh handles it
#   (b) version drift after /plugin update bumped pyproject but the venv still
#       holds the old dist-info → setup.sh resyncs
#   (c) leaked VIRTUAL_ENV from claude-hook-tap pointing at a uv cache env
#       instead of $DIR/.venv → unset before invoking setup
if ! "$DIR/setup.sh" --check 2>/dev/null; then
  log "[WARN] setup --check failed — attempting self-heal"
  if env -u VIRTUAL_ENV "$DIR/setup.sh" >>"$LOG" 2>&1; then
    log "self-heal: setup.sh succeeded"
  else
    log "[ERROR] self-heal failed"
    echo "[ERROR] setup incomplete and self-heal failed. run: bash $DIR/setup.sh" >&2
    exit 1
  fi
fi
log "setup --check passed"

# Strip leaked VIRTUAL_ENV before exec so `uv run --directory` resolves to
# this project's .venv instead of whatever cache env the parent shell points at.
log "exec: env -u VIRTUAL_ENV uv run --directory $DIR frontprompt daemon $*"
exec env -u VIRTUAL_ENV uv run --directory "$DIR" frontprompt daemon "$@" 2>> "$LOG"
