"""Windows keystroke and clipboard backend (ctypes / SendInput)."""

import ctypes
from ctypes import wintypes

_user32 = ctypes.WinDLL("user32", use_last_error=True)
_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
# 64-bit: default restype is c_int and truncates pointer handles.
_user32.OpenClipboard.argtypes = [wintypes.HWND]
_user32.OpenClipboard.restype = wintypes.BOOL
_user32.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]
_user32.SetClipboardData.restype = wintypes.HANDLE
_user32.EmptyClipboard.argtypes = []
_user32.EmptyClipboard.restype = wintypes.BOOL
_user32.CloseClipboard.argtypes = []
_user32.CloseClipboard.restype = wintypes.BOOL
_user32.SendInput.argtypes = [wintypes.UINT, ctypes.c_void_p, ctypes.c_int]
_user32.SendInput.restype = wintypes.UINT
_kernel32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
_kernel32.GlobalAlloc.restype = wintypes.HGLOBAL
_kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
_kernel32.GlobalLock.restype = ctypes.c_void_p
_kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
_kernel32.GlobalUnlock.restype = wintypes.BOOL
_kernel32.GlobalFree.argtypes = [wintypes.HGLOBAL]
_kernel32.GlobalFree.restype = wintypes.HGLOBAL

INPUT_KEYBOARD = 1
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004
CF_UNICODETEXT = 13
GMEM_MOVEABLE = 0x0002
VK_CONTROL = 0x11
VK_SHIFT = 0x10
VK_RETURN = 0x0D
VK_TAB = 0x09
VK_V = 0x56
_ULONG_PTR = ctypes.c_size_t


class _KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", _ULONG_PTR),
    ]


class _MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", _ULONG_PTR),
    ]


class _HARDWAREINPUT(ctypes.Structure):
    _fields_ = [
        ("uMsg", wintypes.DWORD),
        ("wParamL", wintypes.WORD),
        ("wParamH", wintypes.WORD),
    ]


class _INPUT_UNION(ctypes.Union):
    _fields_ = [
        ("ki", _KEYBDINPUT),
        ("mi", _MOUSEINPUT),
        ("hi", _HARDWAREINPUT),
    ]


class _INPUT(ctypes.Structure):
    _anonymous_ = ("union",)
    _fields_ = [
        ("type", wintypes.DWORD),
        ("union", _INPUT_UNION),
    ]


def _win_send_inputs(events):
    """Send a list of KEYBDINPUT specs [(vk, scan, flags), ...]."""
    n = len(events)
    arr = (_INPUT * n)()
    for i, (vk, scan, flags) in enumerate(events):
        arr[i].type = INPUT_KEYBOARD
        arr[i].ki = _KEYBDINPUT(vk, scan, flags, 0, 0)
    sent = _user32.SendInput(n, ctypes.byref(arr), ctypes.sizeof(_INPUT))
    if sent != n:
        err = ctypes.get_last_error()
        raise OSError(f"SendInput failed ({sent}/{n}), GetLastError={err}")


def _win_key_tap(vk, scan=0, flags=0):
    _win_send_inputs(
        [
            (vk, scan, flags),
            (vk, scan, flags | KEYEVENTF_KEYUP),
        ]
    )


def _win_unicode_char(ch):
    code = ord(ch)
    _win_send_inputs(
        [
            (0, code, KEYEVENTF_UNICODE),
            (0, code, KEYEVENTF_UNICODE | KEYEVENTF_KEYUP),
        ]
    )


def _win_chord(keys_down_vk):
    """Press modifier keys + V in order, then release in reverse."""
    events = [(vk, 0, 0) for vk in keys_down_vk]
    events += [(vk, 0, KEYEVENTF_KEYUP) for vk in reversed(keys_down_vk)]
    _win_send_inputs(events)


def win_set_clipboard(text: str) -> None:
    """Put Unicode text on the Windows clipboard."""
    if not _user32.OpenClipboard(None):
        raise OSError(f"OpenClipboard failed, GetLastError={ctypes.get_last_error()}")
    try:
        if not _user32.EmptyClipboard():
            raise OSError(
                f"EmptyClipboard failed, GetLastError={ctypes.get_last_error()}"
            )
        data = text.encode("utf-16-le") + b"\x00\x00"
        h = _kernel32.GlobalAlloc(GMEM_MOVEABLE, len(data))
        if not h:
            raise OSError("GlobalAlloc failed")
        p = _kernel32.GlobalLock(h)
        if not p:
            _kernel32.GlobalFree(h)
            raise OSError("GlobalLock failed")
        try:
            ctypes.memmove(p, data, len(data))
        finally:
            _kernel32.GlobalUnlock(h)
        if not _user32.SetClipboardData(CF_UNICODETEXT, h):
            _kernel32.GlobalFree(h)
            raise OSError(
                f"SetClipboardData failed, GetLastError={ctypes.get_last_error()}"
            )
        # Ownership of h transfers to the system on success.
    finally:
        _user32.CloseClipboard()


def win_type_text(text: str) -> None:
    """Type text via SendInput (Unicode). Newlines/tabs become real keys."""
    i = 0
    n = len(text)
    while i < n:
        ch = text[i]
        if ch == "\r" and i + 1 < n and text[i + 1] == "\n":
            _win_key_tap(VK_RETURN)
            i += 2
            continue
        if ch in ("\n", "\r"):
            _win_key_tap(VK_RETURN)
        elif ch == "\t":
            _win_key_tap(VK_TAB)
        else:
            _win_unicode_char(ch)
        i += 1


def win_paste_chord(paste_key: str) -> None:
    if paste_key == "ctrl+shift+v":
        _win_chord([VK_SHIFT, VK_CONTROL, VK_V])
    else:
        _win_chord([VK_CONTROL, VK_V])


def win_press_enter() -> None:
    _win_key_tap(VK_RETURN)
