"""macOS keystroke (AppleScript/System Events) and clipboard (pbcopy) backend."""

import subprocess
import time


def _osascript(script: str) -> None:
    subprocess.run(
        ["osascript", "-e", script],
        check=True,
        timeout=30,
    )


def _escape_applescript(s: str) -> str:
    return s.replace("\\", "\\\\").replace('"', '\\"')


def macos_type_text(text: str) -> None:
    """Type text via System Events keystroke. Needs Accessibility permission."""
    parts = []
    buf = []
    i = 0
    n = len(text)
    while i < n:
        ch = text[i]
        if ch == "\r" and i + 1 < n and text[i + 1] == "\n":
            if buf:
                parts.append(f'keystroke "{_escape_applescript("".join(buf))}"')
                buf = []
            parts.append("key code 36")  # Return
            i += 2
            continue
        if ch in ("\n", "\r"):
            if buf:
                parts.append(f'keystroke "{_escape_applescript("".join(buf))}"')
                buf = []
            parts.append("key code 36")  # Return
        elif ch == "\t":
            if buf:
                parts.append(f'keystroke "{_escape_applescript("".join(buf))}"')
                buf = []
            parts.append("key code 48")  # Tab
        else:
            buf.append(ch)
        i += 1
    if buf:
        parts.append(f'keystroke "{_escape_applescript("".join(buf))}"')
    if not parts:
        return
    script = 'tell application "System Events"\n{}\nend tell'.format(
        "\n".join(parts)
    )
    _osascript(script)


def macos_set_clipboard(text: str) -> None:
    subprocess.run(
        ["pbcopy"],
        input=text.encode("utf-8"),
        check=True,
        timeout=5,
    )


def macos_paste_chord(paste_key: str) -> None:
    # Config keys ('ctrl+v' / 'ctrl+shift+v') map onto Cmd on macOS.
    modifiers = "using {command down}"
    if paste_key == "ctrl+shift+v":
        modifiers = "using {command down, shift down}"
    _osascript(f'tell application "System Events" to keystroke "v" {modifiers}')


def macos_press_enter() -> None:
    _osascript('tell application "System Events" to key code 36')


def copy_then_optional_paste(
    text: str, *, auto_paste: bool, force_paste: bool, paste_key: str
) -> None:
    macos_set_clipboard(text)
    time.sleep(0.1)
    if auto_paste or force_paste:
        macos_paste_chord(paste_key)
        time.sleep(0.25)