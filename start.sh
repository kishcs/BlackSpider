#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────
#  BlackSpider Terminal – App Server Startup Script
# ─────────────────────────────────────────────────────────────────
set -euo pipefail

# ── Directory where this script lives ──
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$SCRIPT_DIR/.venv"

# ── Activate virtual environment ───────────────────────────────
if [ ! -d "$VENV_DIR" ]; then
    echo "✖ Virtual environment not found. Run ./setup.sh first."
    exit 1
fi

# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"

# ── Environment Variables ──────────────────────────────────────
# Root directory for terminal sessions and file browsing.
export TERMINAL_ROOT="${TERMINAL_ROOT:-$SCRIPT_DIR}"

# Shell launched inside each terminal tab.
export TERMINAL_SHELL="${TERMINAL_SHELL:-/bin/bash}"

# Seconds before an idle (detached) terminal session is reaped.
export TERMINAL_IDLE_TTL_SECONDS="${TERMINAL_IDLE_TTL_SECONDS:-1800}"

# ── Server Configuration ───────────────────────────────────────
HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-8000}"
WORKERS="${WORKERS:-1}"
LOG_LEVEL="${LOG_LEVEL:-info}"
RELOAD="${RELOAD:-false}"

# ── Build uvicorn command ──────────────────────────────────────
UVICORN_ARGS=(
    "app.main:app"
    "--host" "$HOST"
    "--port" "$PORT"
    "--workers" "$WORKERS"
    "--log-level" "$LOG_LEVEL"
)

if [ "$RELOAD" = "true" ]; then
    UVICORN_ARGS+=("--reload")
fi

# ── Launch ─────────────────────────────────────────────────────
echo "──────────────────────────────────────────────"
echo "  BlackSpider Terminal"
echo "  http://${HOST}:${PORT}"
echo "──────────────────────────────────────────────"
echo "  TERMINAL_ROOT            = $TERMINAL_ROOT"
echo "  TERMINAL_SHELL           = $TERMINAL_SHELL"
echo "  TERMINAL_IDLE_TTL_SECONDS = $TERMINAL_IDLE_TTL_SECONDS"
echo "  WORKERS                  = $WORKERS"
echo "  RELOAD                   = $RELOAD"
echo "──────────────────────────────────────────────"

cd "$SCRIPT_DIR"
exec uvicorn "${UVICORN_ARGS[@]}"
