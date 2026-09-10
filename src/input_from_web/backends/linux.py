"""Linux ydotool / wl-copy injection backend."""

import subprocess
import time


def linux_type_text(text: str) -> None:
    subprocess.run(
        ["ydotool", "type", "--key-delay", "0", "--", text],
        check=True,
        timeout=30,
    )


def linux_set_clipboard(text: str) -> None:
    subprocess.run(
        ["wl-copy", "--", text],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=True,
        timeout=5,
    )


def linux_paste_chord(paste_key: str) -> None:
    # 29=Ctrl, 42=Shift, 47=V (Linux x86 keycodes).
    if paste_key == "ctrl+shift+v":
        chord = ["42:1", "29:1", "47:1", "47:0", "29:0", "42:0"]
    else:
        chord = ["29:1", "47:1", "47:0", "29:0"]
    subprocess.run(
        ["ydotool", "key", "-d", "100", *chord],
        check=True,
        timeout=5,
    )


def linux_press_enter() -> None:
    subprocess.run(
        ["ydotool", "key", "-d", "50", "28:1", "28:0"],  # 28 = Return
        check=True,
        timeout=5,
    )


def copy_then_optional_paste(text: str, *, auto_paste: bool, force_paste: bool, paste_key: str) -> None:
    linux_set_clipboard(text)
    time.sleep(0.1)
    if auto_paste or force_paste:
        linux_paste_chord(paste_key)
        time.sleep(0.25)
