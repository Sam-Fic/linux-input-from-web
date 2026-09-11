"""Shared test fixtures: fake Win32 DLL layer and proc-call capture helper."""

import ctypes
import sys
import types

import pytest


class FakeWin32Proc:
    """Callable stand-in for a Win32 exported function.

    Records invocations; returns 1 (truthy) by default so success paths
    proceed. Set `return_values[fn]` to override per function, either with a
    plain value or a callable receiving the call args.
    """

    def __init__(self, name, owner):
        self.name = name
        self.owner = owner
        self.argtypes = ()
        self.restype = None

    def __call__(self, *args, **kwargs):
        self.owner.calls.append((self.name, args, kwargs))
        if self.name in self.owner.return_values:
            target = self.owner.return_values[self.name]
            return target(*args, **kwargs) if callable(target) else target
        return 1


class FakeWin32DLL:
    """Duck-typed replacement for ctypes.WinDLL used by the windows backend."""

    def __init__(self, dll_name, *, use_last_error=False):
        self.dll_name = dll_name
        self.calls = []
        self.return_values = {}

    def __getattr__(self, name):
        if name.startswith("_"):
            raise AttributeError(name)
        return FakeWin32Proc(name, self)


@pytest.fixture
def fake_win32(monkeypatch):
    """Return a factory mapping dll name -> FakeWin32DLL, and patch ctypes.

    After the fixture, `import input_from_web.backends.windows` resolves all
    its ``ctypes.WinDLL(...)`` calls to fakes, so backend logic can be tested
    on any host OS. The fake memmove is swapped for a recorder that exposes
    the copied payload and size.
    """

    dlls = {}
    memmove_calls = []

    def fake_windll(name, **kwargs):
        dll = FakeWin32DLL(name, **kwargs)
        if name == "user32":
            # SendInput returns the number of events actually inserted.
            dll.return_values["SendInput"] = lambda n, p, s: n
        dlls[name] = dll
        return dll

    def fake_memmove(dst, src, n):
        memmove_calls.append((dst, src, n))
        return n

    monkeypatch.setattr(ctypes, "WinDLL", fake_windll, raising=False)
    monkeypatch.setattr(ctypes, "memmove", fake_memmove, raising=False)
    monkeypatch.setattr(ctypes, "get_last_error", lambda: 0, raising=False)
    return dlls


def install_fake_backend(monkeypatch, mod_name, funcs):
    """Register a fake platform backend module in sys.modules.

    Used by the inject_text routing tests so each platform branch can be
    exercised on any OS without importing ctypes-backed (windows) or
    subprocess-dependent (linux/macos) real modules. Every named function is
    a recorder that appends its name to ``mod.calls``.
    """

    mod = types.ModuleType(mod_name)
    mod.calls = []
    for name in funcs:
        setattr(
            mod,
            name,
            lambda *a, _name=name, _calls=mod.calls: _calls.append(_name),
        )
    monkeypatch.setitem(sys.modules, mod_name, mod)
    return mod