"""Platform-aware text injection orchestration."""

import time

from .paths import IS_WIN
from .state import Runtime


def _is_ascii(text: str) -> bool:
    try:
        text.encode("ascii")
    except UnicodeEncodeError:
        return False
    return True


def _strip_trailing_newlines(text: str) -> str:
    """Avoid double-Enter when auto-Enter is on and text already ends with newlines."""
    return text.rstrip("\r\n")


def inject_text(runtime: Runtime, text: str) -> None:
    """Inject text using the chosen method (platform-aware)."""
    if IS_WIN:
        from .backends import windows as win

        payload = _strip_trailing_newlines(text) if runtime.auto_press_enter else text
        if not payload and text:
            payload = text  # text was only newlines; keep original behavior

        if runtime.method == "type" and _is_ascii(payload):
            win.win_type_text(payload)
        else:
            win.win_set_clipboard(payload)
            time.sleep(0.1)
            if runtime.auto_paste or (
                runtime.method == "type" and not _is_ascii(payload)
            ):
                win.win_paste_chord(runtime.paste_key)
                time.sleep(0.25)
        if runtime.auto_press_enter:
            if runtime.method == "type" and _is_ascii(payload):
                time.sleep(0.05)
            win.win_press_enter()
        return

    from .backends import linux

    if runtime.auto_press_enter:
        text = _strip_trailing_newlines(text)

    if runtime.method == "type" and _is_ascii(text):
        linux.linux_type_text(text)
    else:
        force_paste = runtime.method == "type" and not _is_ascii(text)
        linux.copy_then_optional_paste(
            text,
            auto_paste=runtime.auto_paste,
            force_paste=force_paste,
            paste_key=runtime.paste_key,
        )

    if runtime.auto_press_enter:
        linux.linux_press_enter()
