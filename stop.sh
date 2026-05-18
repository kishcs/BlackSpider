#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────
#  BlackSpider Terminal – Stop Script
# ─────────────────────────────────────────────────────────────────
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PID_FILE="$SCRIPT_DIR/.blackspider.pid"

if [ ! -f "$PID_FILE" ]; then
    echo "✖ No PID file found. BlackSpider does not appear to be running."
    exit 1
fi

PID=$(cat "$PID_FILE")

if ! kill -0 "$PID" 2>/dev/null; then
    echo "✖ Process $PID is not running. Cleaning up stale PID file."
    rm -f "$PID_FILE"
    exit 1
fi

echo "▸ Stopping BlackSpider (PID $PID) …"
kill "$PID"

# Wait up to 10 seconds for graceful shutdown
for i in $(seq 1 10); do
    if ! kill -0 "$PID" 2>/dev/null; then
        rm -f "$PID_FILE"
        echo "✔ BlackSpider stopped."
        exit 0
    fi
    sleep 1
done

# Force kill if still running
echo "▸ Process did not stop gracefully. Sending SIGKILL …"
kill -9 "$PID" 2>/dev/null || true
rm -f "$PID_FILE"
echo "✔ BlackSpider killed."
