"""Unit tests for inject_text platform routing on all three backends.

Each platform branch is exercised on any host OS by registering fake backend
modules in sys.modules and flipping the module-level IS_WIN / IS_MAC flags.
Fake backend functions record ``(name, args, kwargs)`` triples.
"""

import sys
import types

import pytest

from input_from_web import inject
from input_from_web.state import Runtime

BACKEND_MODULES = (
    "input_from_web.backends.windows",
    "input_from_web.backends.macos",
    "input_from_web.backends.linux",
)

BACKEND_FUNCS = {
    "windows": [
        "win_type_text",
        "win_set_clipboard",
        "win_paste_chord",
        "win_press_enter",
    ],
    "macos": [
        "macos_type_text",
        "macos_set_clipboard",
        "macos_paste_chord",
        "macos_press_enter",
        "copy_then_optional_paste",
    ],
    "linux": [
        "linux_type_text",
        "linux_set_clipboard",
        "linux_paste_chord",
        "linux_press_enter",
        "copy_then_optional_paste",
    ],
}


def _make_func(name, rec):
    def func(*args, **kwargs):
        rec.append((name, args, kwargs))

    return func


@pytest.fixture
def fake_backends(monkeypatch):
    """Register recorder fake backends; return {backend_name: module}.

    Both sys.modules AND the parent package attributes are patched: ``from
    .backends import macos`` resolves against package attributes first, which
    would otherwise win over the sys.modules entry once the real module has
    been imported by another test module.
    """

    from input_from_web import backends as backends_pkg

    installed = {}
    for mod_name in BACKEND_MODULES:
        backend = mod_name.rsplit(".", 1)[1]
        mod = types.ModuleType(mod_name)
        mod.calls = []
        for fname in BACKEND_FUNCS[backend]:
            setattr(mod, fname, _make_func(fname, mod.calls))
        monkeypatch.setitem(sys.modules, mod_name, mod)
        monkeypatch.setattr(backends_pkg, backend, mod)
        installed[backend] = mod
    monkeypatch.setattr(inject, "time", types.SimpleNamespace(sleep=lambda *a: None))
    return installed


@pytest.fixture
def rt():
    return Runtime(token="test-token")


def _names(mod):
    return [n for n, _, _ in mod.calls]


# ---------------------------------------------------------------- Windows --


def test_windows_type_ascii(fake_backends, rt, monkeypatch):
    monkeypatch.setattr(inject, "IS_WIN", True)
    monkeypatch.setattr(inject, "IS_MAC", False)
    inject.inject_text(rt, "hello")
    mod = fake_backends["windows"]
    assert _names(mod) == ["win_type_text"]
    assert mod.calls[0][1] == ("hello",)


def test_windows_type_ascii_with_enter(fake_backends, rt, monkeypatch):
    rt.auto_press_enter = True
    monkeypatch.setattr(inject, "IS_WIN", True)
    monkeypatch.setattr(inject, "IS_MAC", False)
    inject.inject_text(rt, "hello")
    assert _names(fake_backends["windows"]) == ["win_type_text", "win_press_enter"]


def test_windows_type_non_ascii_forces_paste(fake_backends, rt, monkeypatch):
    monkeypatch.setattr(inject, "IS_WIN", True)
    monkeypatch.setattr(inject, "IS_MAC", False)
    inject.inject_text(rt, "中文")
    mod = fake_backends["windows"]
    assert _names(mod) == ["win_set_clipboard", "win_paste_chord"]
    assert mod.calls[0][1] == ("中文",)
    assert mod.calls[1][1] == ("ctrl+v",)  # default paste key


def test_windows_clipboard_no_paste(fake_backends, rt, monkeypatch):
    rt.method = "clipboard"
    monkeypatch.setattr(inject, "IS_WIN", True)
    monkeypatch.setattr(inject, "IS_MAC", False)
    inject.inject_text(rt, "hello")
    assert _names(fake_backends["windows"]) == ["win_set_clipboard"]


def test_windows_clipboard_auto_paste(fake_backends, rt, monkeypatch):
    rt.method = "clipboard"
    rt.auto_paste = True
    rt.paste_key = "ctrl+shift+v"
    monkeypatch.setattr(inject, "IS_WIN", True)
    monkeypatch.setattr(inject, "IS_MAC", False)
    inject.inject_text(rt, "hello")
    mod = fake_backends["windows"]
    assert _names(mod) == ["win_set_clipboard", "win_paste_chord"]
    assert mod.calls[1][1] == ("ctrl+shift+v",)


def test_windows_enter_strips_trailing_newlines(fake_backends, rt, monkeypatch):
    rt.auto_press_enter = True
    monkeypatch.setattr(inject, "IS_WIN", True)
    monkeypatch.setattr(inject, "IS_MAC", False)
    inject.inject_text(rt, "hi\n\n")
    mod = fake_backends["windows"]
    assert mod.calls[0][1] == ("hi",)  # newlines stripped, single Enter sent
    assert _names(mod) == ["win_type_text", "win_press_enter"]


def test_windows_enter_only_newlines_keeps_text(fake_backends, rt, monkeypatch):
    rt.auto_press_enter = True
    monkeypatch.setattr(inject, "IS_WIN", True)
    monkeypatch.setattr(inject, "IS_MAC", False)
    inject.inject_text(rt, "\n\n")
    mod = fake_backends["windows"]
    # stripped payload is empty -> original text kept (existing behaviour)
    assert mod.calls[0][1] == ("\n\n",)
    assert _names(mod) == ["win_type_text", "win_press_enter"]


# ------------------------------------------------------------------ macOS --


def test_macos_type_ascii(fake_backends, rt, monkeypatch):
    monkeypatch.setattr(inject, "IS_WIN", False)
    monkeypatch.setattr(inject, "IS_MAC", True)
    inject.inject_text(rt, "hello")
    mod = fake_backends["macos"]
    assert _names(mod) == ["macos_type_text"]
    assert mod.calls[0][1] == ("hello",)


def test_macos_type_non_ascii_forces_paste(fake_backends, rt, monkeypatch):
    monkeypatch.setattr(inject, "IS_WIN", False)
    monkeypatch.setattr(inject, "IS_MAC", True)
    inject.inject_text(rt, "中文")
    mod = fake_backends["macos"]
    assert _names(mod) == ["copy_then_optional_paste"]
    name, args, kwargs = mod.calls[0]
    assert name == "copy_then_optional_paste"
    assert args == ("中文",)
    assert kwargs == {
        "auto_paste": False,
        "force_paste": True,  # method is type but non-ASCII
        "paste_key": "ctrl+v",
    }


def test_macos_clipboard_auto_paste_flags(fake_backends, rt, monkeypatch):
    rt.method = "clipboard"
    rt.auto_paste = True
    rt.paste_key = "ctrl+shift+v"
    monkeypatch.setattr(inject, "IS_WIN", False)
    monkeypatch.setattr(inject, "IS_MAC", True)
    inject.inject_text(rt, "hello")
    mod = fake_backends["macos"]
    assert _names(mod) == ["copy_then_optional_paste"]
    _, args, kwargs = mod.calls[0]
    assert args == ("hello",)
    assert kwargs == {
        "auto_paste": True,
        "force_paste": False,  # clipboard method never forces
        "paste_key": "ctrl+shift+v",
    }


def test_macos_press_enter_strips_and_sends(fake_backends, rt, monkeypatch):
    rt.auto_press_enter = True
    monkeypatch.setattr(inject, "IS_WIN", False)
    monkeypatch.setattr(inject, "IS_MAC", True)
    inject.inject_text(rt, "hi\n")
    mod = fake_backends["macos"]
    assert mod.calls[0][1] == ("hi",)
    assert _names(mod) == ["macos_type_text", "macos_press_enter"]


# ------------------------------------------------------------------ Linux --


def test_linux_type_ascii(fake_backends, rt, monkeypatch):
    monkeypatch.setattr(inject, "IS_WIN", False)
    monkeypatch.setattr(inject, "IS_MAC", False)
    inject.inject_text(rt, "hello")
    mod = fake_backends["linux"]
    assert _names(mod) == ["linux_type_text"]
    assert mod.calls[0][1] == ("hello",)


def test_linux_type_non_ascii_forces_paste(fake_backends, rt, monkeypatch):
    monkeypatch.setattr(inject, "IS_WIN", False)
    monkeypatch.setattr(inject, "IS_MAC", False)
    inject.inject_text(rt, "中文")
    mod = fake_backends["linux"]
    assert _names(mod) == ["copy_then_optional_paste"]
    _, args, kwargs = mod.calls[0]
    assert args == ("中文",)
    assert kwargs["force_paste"] is True
    assert kwargs["auto_paste"] is False


def test_linux_clipboard_no_paste(fake_backends, rt, monkeypatch):
    rt.method = "clipboard"
    monkeypatch.setattr(inject, "IS_WIN", False)
    monkeypatch.setattr(inject, "IS_MAC", False)
    inject.inject_text(rt, "hello")
    mod = fake_backends["linux"]
    assert _names(mod) == ["copy_then_optional_paste"]
    assert mod.calls[0][2] == {
        "auto_paste": False,
        "force_paste": False,
        "paste_key": "ctrl+v",
    }


def test_linux_press_enter(fake_backends, rt, monkeypatch):
    rt.auto_press_enter = True
    monkeypatch.setattr(inject, "IS_WIN", False)
    monkeypatch.setattr(inject, "IS_MAC", False)
    inject.inject_text(rt, "hi")
    assert _names(fake_backends["linux"]) == ["linux_type_text", "linux_press_enter"]