"""Unit tests for the Windows ctypes backend (fake Win32 layer).

The windows module must NOT be imported at collection time: on non-Windows
hosts ``ctypes.WinDLL("user32")`` raises. Every test imports it inside the
``win`` fixture, after the fake_win32 fixture has replaced WinDLL.
"""

import ctypes
import importlib
import sys

import pytest


@pytest.fixture
def win(fake_win32):
    """Import the windows backend against the fresh fake Win32 DLLs."""
    mod_name = "input_from_web.backends.windows"
    sys.modules.pop(mod_name, None)  # re-import against the new fakes
    return importlib.import_module(mod_name)


def test_send_inputs_success(win, fake_win32):
    events = [(0x11, 0, 0), (0x11, 0, 0x0002)]
    win._win_send_inputs(events)
    user32 = fake_win32["user32"]
    calls = [c for c in user32.calls if c[0] == "SendInput"]
    assert len(calls) == 1
    n, _ptr, size = calls[0][1]
    assert n == 2
    assert size == ctypes.sizeof(win._INPUT)


def test_send_inputs_partial_failure(win, fake_win32):
    fake_win32["user32"].return_values["SendInput"] = lambda n, p, s: 0
    with pytest.raises(OSError, match="SendInput failed"):
        win._win_send_inputs([(0x11, 0, 0)])


def test_key_tap_down_then_up(win):
    sent = []
    win._win_send_inputs = sent.append
    win._win_key_tap(win.VK_RETURN)
    assert sent == [[(win.VK_RETURN, 0, 0), (win.VK_RETURN, 0, win.KEYEVENTF_KEYUP)]]


def test_unicode_char_uses_unicode_flag(win):
    sent = []
    win._win_send_inputs = sent.append
    win._win_unicode_char("A")
    assert sent == [
        [(0, ord("A"), win.KEYEVENTF_UNICODE),
         (0, ord("A"), win.KEYEVENTF_UNICODE | win.KEYEVENTF_KEYUP)]
    ]


def test_chord_down_then_reverse_up(win, fake_win32):
    win._win_chord([win.VK_SHIFT, win.VK_CONTROL, win.VK_V])
    user32 = fake_win32["user32"]
    call = [c for c in user32.calls if c[0] == "SendInput"][0][1]
    assert call[0] == 6  # 3 down + 3 up


def test_type_text_crlf_enter_tab_plain(win):
    flat = []
    win._win_send_inputs = lambda evs: flat.extend(evs)
    win.win_type_text("a\r\nb\tc")
    assert (win.VK_RETURN, 0, 0) in flat
    assert (win.VK_RETURN, 0, win.KEYEVENTF_KEYUP) in flat
    assert (win.VK_TAB, 0, 0) in flat
    assert (0, ord("a"), win.KEYEVENTF_UNICODE) in flat
    assert (0, ord("c"), win.KEYEVENTF_UNICODE) in flat


def test_type_text_lone_newline(win):
    flat = []
    win._win_send_inputs = lambda evs: flat.extend(evs)
    win.win_type_text("x\n")
    n_enter_press = sum(1 for e in flat if e[0] == win.VK_RETURN and e[2] == 0)
    assert n_enter_press == 1  # the lone \n becomes a single Enter press
    assert (win.VK_RETURN, 0, win.KEYEVENTF_KEYUP) in flat


def test_paste_chord_ctrl_v(win, fake_win32):
    win.win_paste_chord("ctrl+v")
    user32 = fake_win32["user32"]
    call = [c for c in user32.calls if c[0] == "SendInput"][0][1]
    assert call[0] == 4  # Ctrl, V down; V, Ctrl up


def test_paste_chord_ctrl_shift_v(win, fake_win32):
    win.win_paste_chord("ctrl+shift+v")
    user32 = fake_win32["user32"]
    call = [c for c in user32.calls if c[0] == "SendInput"][0][1]
    assert call[0] == 6  # Shift, Ctrl, V down; V, Ctrl, Shift up


def test_press_enter_sends_two_events(win, fake_win32):
    win.win_press_enter()
    user32 = fake_win32["user32"]
    call = [c for c in user32.calls if c[0] == "SendInput"][0][1]
    assert call[0] == 2  # down + up


def test_set_clipboard_payload_size_and_order(win, fake_win32):
    win.win_set_clipboard("Hi")
    user32 = fake_win32["user32"]
    names = [c[0] for c in user32.calls]
    assert names[:3] == ["OpenClipboard", "EmptyClipboard", "SetClipboardData"]
    assert names[-1] == "CloseClipboard"
    # payload is UTF-16-LE + NUL terminator at the kernel32 level
    kernel32 = fake_win32["kernel32"]
    alloc = [c for c in kernel32.calls if c[0] == "GlobalAlloc"]
    assert alloc and alloc[0][1][1] == len("Hi".encode("utf-16-le")) + 2


def test_set_clipboard_open_failure(win, fake_win32):
    fake_win32["user32"].return_values["OpenClipboard"] = lambda h: 0
    with pytest.raises(OSError, match="OpenClipboard failed"):
        win.win_set_clipboard("x")