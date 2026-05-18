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

# Default shell prompt for terminal sessions.
export TERMINAL_PS1="${TERMINAL_PS1:-\\u@\\h:\\W \\$ }"

# Seconds before an idle (detached) terminal session is reaped.
export TERMINAL_IDLE_TTL_SECONDS="${TERMINAL_IDLE_TTL_SECONDS:-1800}"

# CORS allowed origins (comma-separated). Default: * (all origins).
export CORS_ORIGINS="${CORS_ORIGINS:-*}"

# ── Server Configuration ───────────────────────────────────────
export HOST="${HOST:-0.0.0.0}"
export PORT="${PORT:-8000}"
export WORKERS="${WORKERS:-1}"
export LOG_LEVEL="${LOG_LEVEL:-info}"
export RELOAD="${RELOAD:-false}"

# ── Launch ─────────────────────────────────────────────────────
echo "──────────────────────────────────────────────"
echo "  BlackSpider Terminal"
echo "  http://${HOST}:${PORT}"
echo "──────────────────────────────────────────────"
echo "  TERMINAL_ROOT            = $TERMINAL_ROOT"
echo "  TERMINAL_SHELL           = $TERMINAL_SHELL"
echo "  TERMINAL_IDLE_TTL_SECONDS = $TERMINAL_IDLE_TTL_SECONDS"
echo "  CORS_ORIGINS             = $CORS_ORIGINS"
echo "  WORKERS                  = $WORKERS"
echo "  RELOAD                   = $RELOAD"
echo "──────────────────────────────────────────────"

PID_FILE="$SCRIPT_DIR/.blackspider.pid"

# ── Check if already running ───────────────────────────────────
if [ -f "$PID_FILE" ]; then
    OLD_PID=$(cat "$PID_FILE")
    if kill -0 "$OLD_PID" 2>/dev/null; then
        echo "✖ BlackSpider is already running (PID $OLD_PID). Run ./stop.sh first."
        exit 1
    fi
    rm -f "$PID_FILE"
fi

# ── Start ──────────────────────────────────────────────────────
cd "$SCRIPT_DIR"
python -m app.main &
APP_PID=$!
echo "$APP_PID" > "$PID_FILE"
echo "  PID                      = $APP_PID"
echo "──────────────────────────────────────────────"

# ── Wait for process and clean up on exit ──────────────────────
trap 'rm -f "$PID_FILE"' EXIT
wait "$APP_PID"
