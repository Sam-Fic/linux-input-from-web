"""Install/uninstall user autostart entries (Windows Startup / Linux .desktop)."""

import os
import shlex
import shutil

from xml.sax.saxutils import escape

from .paths import (
    AUTOSTART_DIR,
    AUTOSTART_FILE,
    IS_MAC,
    IS_WIN,
    SCRIPT_DIR,
)

# Terminal candidates across distributions/desktops.
# Each entry: (name, executable, arg_style)
# arg_style: "bash_c"  ->  exe -- bash -c 'CMD'
#            "dash_e"  ->  exe -e 'CMD'
#            "ptyxis"  ->  ptyxis --new-window -T TITLE -x 'CMD'
TERMINAL_CANDIDATES = [
    ("ptyxis", "ptyxis", "ptyxis"),
    ("gnome-terminal", "gnome-terminal", "bash_c"),
    ("konsole", "konsole", "dash_e"),
    ("xfce4-terminal", "xfce4-terminal", "dash_e"),
    ("mate-terminal", "mate-terminal", "bash_c"),
    ("lxterminal", "lxterminal", "dash_e"),
    ("terminator", "terminator", "bash_c"),
    ("alacritty", "alacritty", "dash_e"),
    ("x-terminal-emulator", "x-terminal-emulator", "dash_e"),
]


def detect_terminal():
    """Return (exe, arg_style) for the first available terminal, or (None, None)."""
    for _name, exe, style in TERMINAL_CANDIDATES:
        if shutil.which(exe):
            return exe, style
    return None, None


def build_desktop_exec(terminal_exe, arg_style, title, script_cmd):
    """Build the Exec= line for the autostart .desktop file."""
    countdown = (
        "echo 'Starting in 10...'; "
        "for i in 10 9 8 7 6 5 4 3 2 1; do echo $i; sleep 1; done; "
        "clear; "
    )
    inner = f"bash -lc {shlex.quote(countdown + script_cmd)}"
    if arg_style == "ptyxis":
        return (
            f"{terminal_exe} --new-window -T {shlex.quote(title)} "
            f"-x {shlex.quote(inner)}"
        )
    elif arg_style == "bash_c":
        return f"{terminal_exe} -T {shlex.quote(title)} -- {inner}"
    else:
        return f"{terminal_exe} -e {shlex.quote(inner)}"


DESKTOP_TEMPLATE = """\
[Desktop Entry]
Type=Application
Name=Input from Web
Comment=Type on your phone, inject into focused desktop app
Exec={exec_line}
Terminal=true
X-GNOME-Autostart-enabled=true
"""


WIN_AUTOSTART_TEMPLATE = """\
@echo off
title Input from Web
cd /d "{script_dir}"
echo Starting Input from Web in 10 seconds... Press Ctrl+C to cancel.
timeout /t 10 >nul
if exist "{script_dir}\\run.bat" (
    call "{script_dir}\\run.bat"
) else (
    python "{script_dir}\\input-from-web.py"
)
"""

MAC_AUTOSTART_TEMPLATE = """\
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" \
"http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.input-from-web</string>
    <key>ProgramArguments</key>
    <array>
        <string>/usr/bin/osascript</string>
        <string>-e</string>
        <string>tell application "Terminal" to do script "{script_path}"</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>LimitLoadToSessionType</key>
    <string>Aqua</string>
</dict>
</plist>
"""


def install_autostart():
    """Create the user autostart entry for this OS. Returns (ok, message)."""
    if IS_WIN:
        os.makedirs(AUTOSTART_DIR, exist_ok=True)
        content = WIN_AUTOSTART_TEMPLATE.format(script_dir=SCRIPT_DIR)
        with open(AUTOSTART_FILE, "w", encoding="utf-8", newline="\r\n") as f:
            f.write(content)
        return True, f"Autostart installed: {AUTOSTART_FILE}"

    if IS_MAC:
        os.makedirs(AUTOSTART_DIR, exist_ok=True)
        script_path = escape(os.path.join(SCRIPT_DIR, "run.sh"))
        content = MAC_AUTOSTART_TEMPLATE.format(script_path=script_path)
        with open(AUTOSTART_FILE, "w", encoding="utf-8") as f:
            f.write(content)
        return True, f"Autostart installed: {AUTOSTART_FILE}"

    terminal_exe, arg_style = detect_terminal()
    if not terminal_exe:
        return False, (
            "No supported terminal emulator found. Install gnome-terminal, "
            "konsole, xfce4-terminal, ptyxis, or another and try again."
        )
    script_cmd = f'"{SCRIPT_DIR}/run.sh"'
    exec_line = build_desktop_exec(terminal_exe, arg_style, "Input from Web", script_cmd)
    os.makedirs(AUTOSTART_DIR, exist_ok=True)
    content = DESKTOP_TEMPLATE.format(exec_line=exec_line)
    with open(AUTOSTART_FILE, "w") as f:
        f.write(content)
    return True, f"Autostart installed: {AUTOSTART_FILE}\n  Exec: {exec_line}"


def uninstall_autostart():
    """Remove the user autostart entry if present. Returns (ok, message)."""
    if os.path.exists(AUTOSTART_FILE):
        os.remove(AUTOSTART_FILE)
        return True, f"Autostart removed: {AUTOSTART_FILE}"
    return True, "Autostart was not installed (nothing to remove)."


def autostart_installed():
    return os.path.exists(AUTOSTART_FILE)
