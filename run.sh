#!/usr/bin/env bash
set -euo pipefail

DIR="$(cd "$(dirname "$0")" && pwd)"

# Ensure ydotoold is running (needs /dev/uinput access)
if ! pgrep -x ydotoold > /dev/null 2>&1; then
    echo "Starting ydotoold (requires sudo for /dev/uinput)..."
    sudo ydotoold &
    sleep 0.5
    echo "ydotoold started."
fi

# Ensure virtual environment exists
if [ ! -d "$DIR/venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv "$DIR/venv"
    echo "Installing dependencies..."
    "$DIR/venv/bin/pip" install --quiet flask qrcode
fi

exec "$DIR/venv/bin/python" "$DIR/input-from-web.py" "$@"
