#!/usr/bin/env bash
set -euo pipefail

DIR="$(cd "$(dirname "$0")" && pwd)"

# ydotool is Linux-only; macOS uses the built-in AppleScript/pbcopy backends.
if [ "$(uname -s)" != "Darwin" ]; then
    # Ensure ydotoold is running (needs /dev/uinput access)
    if ! pgrep -x ydotoold > /dev/null 2>&1; then
        echo "Starting ydotoold (requires sudo for /dev/uinput)..."
        sudo ydotoold &
        sleep 0.5
        echo "ydotoold started."
    fi
fi

# Ensure virtual environment exists
if [ ! -d "$DIR/venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv "$DIR/venv"
fi

# Install deps if missing (covers a pre-existing but incomplete venv)
if ! "$DIR/venv/bin/python" -c "import flask, qrcode" >/dev/null 2>&1; then
    echo "Installing dependencies..."
    "$DIR/venv/bin/pip" install --quiet flask qrcode
fi

export PYTHONPATH="$DIR/src${PYTHONPATH:+:$PYTHONPATH}"
exec "$DIR/venv/bin/python" -m input_from_web "$@"
