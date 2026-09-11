"""Entry point for the py2app macOS .app bundle.

When launched from Finder (no arguments), the app re-launches itself inside a
Terminal window so the QR code and URLs stay visible. When run from a terminal
or with explicit arguments (e.g. --help), it runs directly.
"""
import os
import subprocess
import sys


def _launch_in_terminal(exe: str) -> None:
    quoted = exe.replace("\\", "\\\\").replace('"', '\\"')
    script = f'tell application "Terminal" to do script "{quoted}"'
    subprocess.run(["osascript", "-e", script], check=True)


def _gui_launch() -> bool:
    if len(sys.argv) > 1:
        return False
    try:
        return not sys.stdin.isatty()
    except (AttributeError, OSError):
        return True


def main() -> int:
    if _gui_launch() and not os.environ.get("IFW_ALREADY_IN_TERMINAL"):
        _launch_in_terminal(sys.executable)
        return 0

    from input_from_web.cli import main as cli_main

    return cli_main() or 0


if __name__ == "__main__":
    sys.exit(main())