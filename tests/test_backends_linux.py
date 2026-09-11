"""Unit tests for the Linux ydotool / wl-copy backend."""

import types

from input_from_web.backends import linux as linux_backend


def _fake_subprocess(monkeypatch, recorder):
    """Replace linux_backend.subprocess so DEVNULL is visible and run is recorded."""
    fake = types.ModuleType("fake_subprocess")
    fake.DEVNULL = object()
    fake.run = recorder
    monkeypatch.setattr(linux_backend, "subprocess", fake)


def test_type_text_command(monkeypatch):
    calls = []

    def recorder(cmd, **kwargs):
        calls.append((cmd, kwargs))
        return type("CP", (), {"returncode": 0})()

    _fake_subprocess(monkeypatch, recorder)
    linux_backend.linux_type_text("hello world")
    assert len(calls) == 1
    cmd, kwargs = calls[0]
    assert cmd == ["ydotool", "type", "--key-delay", "0", "--", "hello world"]
    assert kwargs.get("check") is True
    assert kwargs.get("timeout") == 30


def test_set_clipboard_uses_devnull(monkeypatch):
    calls = []

    def recorder(cmd, **kwargs):
        calls.append((cmd, kwargs))

    _fake_subprocess(monkeypatch, recorder)
    linux_backend.linux_set_clipboard("text")
    cmd, kwargs = calls[0]
    assert cmd == ["wl-copy", "--", "text"]
    assert "stdin" in kwargs and "stdout" in kwargs and "stderr" in kwargs
    assert kwargs["check"] is True


def test_paste_chord_ctrl_v(monkeypatch):
    calls = []
    _fake_subprocess(monkeypatch, lambda cmd, **kw: calls.append(cmd))
    linux_backend.linux_paste_chord("ctrl+v")
    assert calls == [["ydotool", "key", "-d", "100", "29:1", "47:1", "47:0", "29:0"]]


def test_paste_chord_ctrl_shift_v(monkeypatch):
    calls = []
    _fake_subprocess(monkeypatch, lambda cmd, **kw: calls.append(cmd))
    linux_backend.linux_paste_chord("ctrl+shift+v")
    assert calls == [[
        "ydotool", "key", "-d", "100",
        "42:1", "29:1", "47:1", "47:0", "29:0", "42:0",
    ]]


def test_press_enter(monkeypatch):
    calls = []
    _fake_subprocess(monkeypatch, lambda cmd, **kw: calls.append(cmd))
    linux_backend.linux_press_enter()
    assert calls == [["ydotool", "key", "-d", "50", "28:1", "28:0"]]


def test_copy_then_optional_paste_no_auto(monkeypatch):
    calls = []

    def rec_clip(t):
        calls.append(("clip", t))

    def rec_paste(k):
        calls.append(("paste", k))

    monkeypatch.setattr(linux_backend, "linux_set_clipboard", rec_clip)
    monkeypatch.setattr(linux_backend, "linux_paste_chord", rec_paste)
    linux_backend.copy_then_optional_paste(
        "x", auto_paste=False, force_paste=False, paste_key="ctrl+v"
    )
    assert calls == [("clip", "x")]


def test_copy_then_optional_paste_auto(monkeypatch):
    calls = []

    def rec_clip(t):
        calls.append(("clip", t))

    def rec_paste(k):
        calls.append(("paste", k))

    monkeypatch.setattr(linux_backend, "linux_set_clipboard", rec_clip)
    monkeypatch.setattr(linux_backend, "linux_paste_chord", rec_paste)
    linux_backend.copy_then_optional_paste(
        "x", auto_paste=True, force_paste=False, paste_key="ctrl+shift+v"
    )
    assert calls == [("clip", "x"), ("paste", "ctrl+shift+v")]