#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────
#  BlackSpider Terminal – Setup Script
#  Creates the virtual environment and installs dependencies.
#  Run once (or after pulling new requirements).
# ─────────────────────────────────────────────────────────────────
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$SCRIPT_DIR/.venv"

# ── Create virtual environment ─────────────────────────────────
if [ ! -d "$VENV_DIR" ]; then
    echo "▸ Creating virtual environment in $VENV_DIR …"
    python3 -m venv "$VENV_DIR"
else
    echo "▸ Virtual environment already exists at $VENV_DIR"
fi

# ── Install / update dependencies ──────────────────────────────
# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"

echo "▸ Installing dependencies …"
pip install -q -r "$SCRIPT_DIR/requirements.txt"

echo "✔ Setup complete. Run ./start.sh to launch the server."
