"""Unit tests for the macOS AppleScript / pbcopy backend."""

import types

from input_from_web.backends import macos as macos_backend


def test_type_text_plain(monkeypatch):
    scripts = []
    monkeypatch.setattr(macos_backend, "_osascript", scripts.append)
    macos_backend.macos_type_text("hello")
    assert len(scripts) == 1
    assert scripts[0].startswith('tell application "System Events"')
    assert 'keystroke "hello"' in scripts[0]
    assert scripts[0].endswith("end tell")


def test_type_text_quote_and_backslash_escaped(monkeypatch):
    scripts = []
    monkeypatch.setattr(macos_backend, "_osascript", scripts.append)
    macos_backend.macos_type_text('Say "hi" \\')
    assert len(scripts) == 1
    assert 'keystroke "Say \\"hi\\" \\\\"' in scripts[0]


def test_type_text_newline_tab_and_crlf(monkeypatch):
    scripts = []
    monkeypatch.setattr(macos_backend, "_osascript", scripts.append)
    macos_backend.macos_type_text("a\n\tb\r\nc\r")
    assert len(scripts) == 1
    s = scripts[0]
    assert s.count("key code 36") == 3  # \n, \r\n, lone \r
    assert "key code 48" in s  # tab
    assert 'keystroke "a"' in s
    assert 'keystroke "b"' in s
    assert 'keystroke "c"' in s


def test_type_text_empty_no_call(monkeypatch):
    scripts = []
    monkeypatch.setattr(macos_backend, "_osascript", scripts.append)
    macos_backend.macos_type_text("")
    assert scripts == []


def test_set_clipboard_uses_pbcopy(monkeypatch):
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append((cmd, kwargs))

    fake = types.ModuleType("fake_subprocess")
    fake.run = fake_run
    monkeypatch.setattr(macos_backend, "subprocess", fake)
    macos_backend.macos_set_clipboard("中文")
    assert calls and calls[0][0] == ["pbcopy"]
    assert calls[0][1]["input"] == "中文".encode("utf-8")


def test_paste_chord_default_cmd_v(monkeypatch):
    scripts = []
    monkeypatch.setattr(macos_backend, "_osascript", scripts.append)
    macos_backend.macos_paste_chord("ctrl+v")
    assert scripts == [
        'tell application "System Events" to keystroke "v" using {command down}'
    ]


def test_paste_chord_ctrl_shift_v(monkeypatch):
    scripts = []
    monkeypatch.setattr(macos_backend, "_osascript", scripts.append)
    macos_backend.macos_paste_chord("ctrl+shift+v")
    assert scripts == [
        'tell application "System Events" to keystroke "v" '
        "using {command down, shift down}"
    ]


def test_press_enter(monkeypatch):
    scripts = []
    monkeypatch.setattr(macos_backend, "_osascript", scripts.append)
    macos_backend.macos_press_enter()
    assert scripts == ['tell application "System Events" to key code 36']


def test_copy_then_optional_paste_no_auto(monkeypatch):
    calls = []

    def rec_clip(t):
        calls.append(("clip", t))

    def rec_paste(k):
        calls.append(("paste", k))

    monkeypatch.setattr(macos_backend, "macos_set_clipboard", rec_clip)
    monkeypatch.setattr(macos_backend, "macos_paste_chord", rec_paste)
    macos_backend.copy_then_optional_paste(
        "x", auto_paste=False, force_paste=False, paste_key="ctrl+v"
    )
    assert calls == [("clip", "x")]


def test_copy_then_optional_paste_force(monkeypatch):
    calls = []

    def rec_clip(t):
        calls.append(("clip", t))

    def rec_paste(k):
        calls.append(("paste", k))

    monkeypatch.setattr(macos_backend, "macos_set_clipboard", rec_clip)
    monkeypatch.setattr(macos_backend, "macos_paste_chord", rec_paste)
    # force_paste is set when method == "type" but payload is non-ASCII
    macos_backend.copy_then_optional_paste(
        "中文", auto_paste=False, force_paste=True, paste_key="ctrl+v"
    )
    assert calls == [("clip", "中文"), ("paste", "ctrl+v")]