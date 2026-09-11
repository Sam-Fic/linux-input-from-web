"""Filesystem and platform paths."""

import os
import sys

IS_WIN = sys.platform == "win32"
IS_MAC = sys.platform == "darwin"

PACKAGE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(PACKAGE_DIR, "static")
TEMPLATES_DIR = os.path.join(PACKAGE_DIR, "templates")

CONFIG_PATH = os.path.expanduser("~/.input-from-web-conf.json")


def _detect_root() -> str:
    # src layout: <root>/src/input_from_web
    candidate = os.path.abspath(os.path.join(PACKAGE_DIR, os.pardir, os.pardir))
    if os.path.exists(os.path.join(candidate, "run.bat")) or os.path.exists(
        os.path.join(candidate, "run.sh")
    ):
        return candidate
    # Debian /usr/share/input-from-web/input_from_web
    return os.path.abspath(os.path.join(PACKAGE_DIR, os.pardir))


ROOT_DIR = _detect_root()
# Used by autostart entries that launch the on-disk runner scripts.
SCRIPT_DIR = ROOT_DIR

if IS_WIN:
    AUTOSTART_DIR = os.path.expandvars(
        r"%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
    )
    AUTOSTART_FILE = os.path.join(AUTOSTART_DIR, "input-from-web.bat")
elif IS_MAC:
    AUTOSTART_DIR = os.path.expanduser("~/Library/LaunchAgents")
    AUTOSTART_FILE = os.path.join(AUTOSTART_DIR, "com.input-from-web.plist")
else:
    AUTOSTART_DIR = os.path.expanduser("~/.config/autostart")
    AUTOSTART_FILE = os.path.join(AUTOSTART_DIR, "input-from-web.desktop")
