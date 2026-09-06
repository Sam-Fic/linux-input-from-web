#!/usr/bin/env python3
"""input-from-web: Type on your phone, inject into focused desktop app."""

import argparse
import json
import os
import secrets
import shlex
import shutil
import socket
import subprocess
import sys
import time

import logging

from flask import Flask, Response, request, abort, send_from_directory
import qrcode

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
app = Flask(__name__)

# Suppress Werkzeug request log for /ping
_werkzeug_log = logging.getLogger("werkzeug")
_orig_log_request = _werkzeug_log.handle

class _PingFilter(logging.Filter):
    def filter(self, record):
        return "/ping" not in record.getMessage()

_werkzeug_log.addFilter(_PingFilter())
TOKEN = secrets.token_urlsafe(32)
USE_TOKEN = True
PERMANENT_LINK = False
METHOD = "type"
AUTO_PASTE = False
PASTE_KEY = "ctrl+v"
AUTO_PRESS_ENTER = False
PROFILE = {}
FULL_CONFIG = None
CURRENT_PROFILE_NAME = None

CONFIG_PATH = os.path.expanduser("~/.input-from-web-conf.json")

AUTOSTART_DIR = os.path.expanduser("~/.config/autostart")
AUTOSTART_FILE = os.path.join(AUTOSTART_DIR, "input-from-web.desktop")

# Terminal candidates across distributions/desktops.
# Each entry: (command, template) where template uses {cmd} for the script to run.
# We prefer `-- bash -c '...'` style; konsole/xfce4-terminal use `-e`.
TERMINAL_CANDIDATES = [
    # (name,        executable,          arg_style)
    # arg_style: "bash_c"  ->  exe -- bash -c 'CMD'
    #            "dash_e"  ->  exe -e 'CMD'
    #            "ptyxis"  ->  ptyxis --new-window -T TITLE -x 'CMD'
    ("ptyxis",            "ptyxis",            "ptyxis"),
    ("gnome-terminal",    "gnome-terminal",    "bash_c"),
    ("konsole",           "konsole",           "dash_e"),
    ("xfce4-terminal",    "xfce4-terminal",    "dash_e"),
    ("mate-terminal",     "mate-terminal",     "bash_c"),
    ("lxterminal",        "lxterminal",        "dash_e"),
    ("terminator",        "terminator",        "bash_c"),
    ("alacritty",         "alacritty",         "dash_e"),
    ("x-terminal-emulator","x-terminal-emulator","dash_e"),
]


def detect_terminal():
    """Return (exe, arg_style) for the first available terminal, or (None, None)."""
    for _name, exe, style in TERMINAL_CANDIDATES:
        if shutil.which(exe):
            return exe, style
    return None, None


def build_desktop_exec(terminal_exe, arg_style, title, script_cmd):
    """Build the Exec= line for the autostart .desktop file."""
    # 10-second countdown so the user sees the terminal window before the
    # Flask server starts and the QR code is printed.
    countdown = (
        "echo 'Starting in 10...'; "
        "for i in 10 9 8 7 6 5 4 3 2 1; do echo $i; sleep 1; done; "
        "clear; "
    )
    inner = f"bash -lc {shlex.quote(countdown + script_cmd)}"
    if arg_style == "ptyxis":
        # ptyxis: -T sets the tab title, -x runs the command in a NEW window.
        # (ptyxis has no `-- cmd` form, so a bare `-- bash -lc ...` opened a
        #  stray second window. Use --new-window -x instead.)
        return (f'{terminal_exe} --new-window -T {shlex.quote(title)} '
                f'-x {shlex.quote(inner)}')
    elif arg_style == "bash_c":
        # e.g. gnome-terminal -T "Title" -- bash -lc '...'
        return f'{terminal_exe} -T {shlex.quote(title)} -- {inner}'
    else:
        # e.g. konsole -e 'bash -lc ...'
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


def install_autostart():
    """Create the user autostart .desktop entry. Returns (ok, message)."""
    terminal_exe, arg_style = detect_terminal()
    if not terminal_exe:
        return False, ("No supported terminal emulator found. Install gnome-terminal, "
                       "konsole, xfce4-terminal, ptyxis, or another and try again.")
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

DEFAULT_CONFIG = {
    "_comment": [
        "input-from-web configuration file.",
        "",
        "default_profile: which profile to use when --profile is not specified.",
        "",
        "profiles.<name>.method:",
        "  'type'      - ydotool type, simulates keystrokes (default).",
        "  'clipboard' - wl-copy to clipboard, you paste manually.",
        "  Can be overridden with --method on the command line.",
        "",
        "profiles.<name>.auto_paste:",
        "  true  - after wl-copy, simulate a paste keystroke via ydotool (clipboard method only).",
        "  false - clipboard only, you paste manually (default).",
        "  Ignored when method is 'type'. Useful for GUI apps, not terminals.",
        "",
        "profiles.<name>.paste_key:",
        "  'ctrl+v'       - simulate Ctrl+V (default).",
        "  'ctrl+shift+v' - simulate Ctrl+Shift+V instead.",
        "  Only used when auto_paste is true. Independent of auto_press_enter.",
        "  Use Ctrl+Shift+V for terminals, code editors, and apps that ignore Ctrl+V.",
        "",
        "profiles.<name>.auto_press_enter:",
        "  true  - after inject_text, simulate an extra Enter key via ydotool.",
        "  false - do not press Enter (default).",
        "  Independent of auto_paste. Useful for chat boxes / messengers / shells",
        "  that need a submit keystroke after the text is typed or pasted.",
        "",
        "profiles.<name>.port:",
        "  TCP port to listen on (default: 5123).",
        "  Can be overridden with --port on the command line.",
        "",
        "profiles.<name>.use_security_token:",
        "  true  - require a secret token in the URL (default, recommended).",
        "  false - no token, anyone on the network can send input.",
        "          WARNING: only disable on a trusted private network!",
        "",
        "profiles.<name>.voice_send:",
        "  enabled       - true/false to toggle voice command detection.",
        "  delay_seconds - seconds to wait after last edit before auto-triggering.",
        "  send_words    - words that trigger auto-send when typed last (case insensitive).",
        "  clear_words   - words that trigger auto-clear when typed last (case insensitive).",
        "",
        "profiles.<name>.substitutions:",
        "  Keys are phrases to match (case insensitive), values are replacements.",
        "  Applied automatically as you type. Useful for voice dictation.",
        "  Example: {\"full stop\": \".\", \"new line\": \"\\n\"}",
    ],
    "default_profile": "default",
    "profiles": {
        "default": {
            "method": "type",
            "auto_paste": False,
            "paste_key": "ctrl+v",
            "auto_press_enter": False,
            "port": 5123,
            "use_security_token": True,
            "voice_send": {
                "enabled": True,
                "delay_seconds": 1.5,
                "send_words": ["send"],
                "clear_words": ["clear"],
            },
            "substitutions": {
                "full stop": ".",
                "question mark": "?",
                "exclamation mark": "!",
                "comma": ",",
                "colon": ":",
                "semicolon": ";",
                "quote": "\"",
                "new line": "\n",
                "new paragraph": "\n\n",
            },
        }
    },
}


def load_or_create_config(profile_name=None):
    """Load config from disk, creating default if missing. Return (profile, profile_name, full_config)."""
    if not os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, "w") as f:
            json.dump(DEFAULT_CONFIG, f, indent=2, ensure_ascii=False)
        print(f"  Created default config: {CONFIG_PATH}")
        config = DEFAULT_CONFIG
    else:
        with open(CONFIG_PATH) as f:
            config = json.load(f)

    if profile_name is None:
        profile_name = config.get("default_profile", "default")

    profiles = config.get("profiles", {})
    if profile_name not in profiles:
        print(f"Error: profile '{profile_name}' not found in {CONFIG_PATH}", file=sys.stderr)
        print(f"Available profiles: {', '.join(profiles.keys())}", file=sys.stderr)
        sys.exit(1)

    print(f"  Profile: {profile_name}")
    return profiles[profile_name], profile_name, config


def save_config(config):
    """Write config back to disk."""
    with open(CONFIG_PATH, "w") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)


HTML_TEMPLATE = r"""
<!DOCTYPE html>
<html lang="__LANG__">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, interactive-widget=resizes-content">
<meta name="theme-color" content="#6750A4">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<link rel="manifest" href="/manifest.json">
<link rel="icon" href="/icon.svg">
<link rel="apple-touch-icon" href="/icon.svg">
<title>__TITLE__</title>

<!-- Material 3 Expressive (@m3e/web) Fonts -->
<link href="https://fonts.googleapis.com/css2?family=Material+Symbols+Outlined:opsz,wght,FILL,GRAD@24,400,0,0&display=block" rel="stylesheet">

<style>
  /* M3 baseline color schemes (seed #6750A4) in the official --md-sys-color-*
     namespace that @m3e/web DesignTokens consume. Components resolve
     var(--md-sys-color-<role>, <light fallback>) so both schemes must be defined. */
  :root {
    --md-sys-color-primary: #6750A4;
    --md-sys-color-on-primary: #FFFFFF;
    --md-sys-color-primary-container: #EADDFF;
    --md-sys-color-on-primary-container: #21005D;
    --md-sys-color-primary-fixed: #EADDFF;
    --md-sys-color-primary-fixed-dim: #D0BCFF;
    --md-sys-color-on-primary-fixed: #21005D;
    --md-sys-color-on-primary-fixed-variant: #4F378B;
    --md-sys-color-secondary: #625B71;
    --md-sys-color-on-secondary: #FFFFFF;
    --md-sys-color-secondary-container: #E8DEF8;
    --md-sys-color-on-secondary-container: #1D192B;
    --md-sys-color-secondary-fixed: #E8DEF8;
    --md-sys-color-secondary-fixed-dim: #CCC2DC;
    --md-sys-color-on-secondary-fixed: #1D192B;
    --md-sys-color-on-secondary-fixed-variant: #4A4458;
    --md-sys-color-tertiary: #7D5260;
    --md-sys-color-on-tertiary: #FFFFFF;
    --md-sys-color-tertiary-container: #FFD8E4;
    --md-sys-color-on-tertiary-container: #31111D;
    --md-sys-color-tertiary-fixed: #FFD8E4;
    --md-sys-color-tertiary-fixed-dim: #EFB8C8;
    --md-sys-color-on-tertiary-fixed: #31111D;
    --md-sys-color-on-tertiary-fixed-variant: #633B48;
    --md-sys-color-error: #B3261E;
    --md-sys-color-on-error: #FFFFFF;
    --md-sys-color-error-container: #F9DEDC;
    --md-sys-color-on-error-container: #410E0B;
    --md-sys-color-surface: #FEF7FF;
    --md-sys-color-on-surface: #1D1B20;
    --md-sys-color-surface-variant: #E7E0EC;
    --md-sys-color-on-surface-variant: #49454F;
    --md-sys-color-surface-dim: #DED8E1;
    --md-sys-color-surface-bright: #FEF7FF;
    --md-sys-color-surface-container-lowest: #FFFFFF;
    --md-sys-color-surface-container-low: #F7F2FA;
    --md-sys-color-surface-container: #F3EDF7;
    --md-sys-color-surface-container-high: #ECE6F0;
    --md-sys-color-surface-container-highest: #E6E0E9;
    --md-sys-color-outline: #79747E;
    --md-sys-color-outline-variant: #CAC4D0;
    --md-sys-color-inverse-surface: #313033;
    --md-sys-color-inverse-on-surface: #F4EFF4;
    --md-sys-color-inverse-primary: #D0BCFF;
    --md-sys-color-scrim: #000000;
    --md-sys-color-shadow: #000000;
  }
  @media (prefers-color-scheme: dark) {
    :root {
      --md-sys-color-primary: #D0BCFF;
      --md-sys-color-on-primary: #381E72;
      --md-sys-color-primary-container: #4F378B;
      --md-sys-color-on-primary-container: #EADDFF;
      --md-sys-color-primary-fixed: #EADDFF;
      --md-sys-color-primary-fixed-dim: #D0BCFF;
      --md-sys-color-on-primary-fixed: #21005D;
      --md-sys-color-on-primary-fixed-variant: #4F378B;
      --md-sys-color-secondary: #CCC2DC;
      --md-sys-color-on-secondary: #332D41;
      --md-sys-color-secondary-container: #4A4458;
      --md-sys-color-on-secondary-container: #E8DEF8;
      --md-sys-color-secondary-fixed: #E8DEF8;
      --md-sys-color-secondary-fixed-dim: #CCC2DC;
      --md-sys-color-on-secondary-fixed: #1D192B;
      --md-sys-color-on-secondary-fixed-variant: #4A4458;
      --md-sys-color-tertiary: #EFB8C8;
      --md-sys-color-on-tertiary: #492532;
      --md-sys-color-tertiary-container: #633B48;
      --md-sys-color-on-tertiary-container: #FFD8E4;
      --md-sys-color-tertiary-fixed: #FFD8E4;
      --md-sys-color-tertiary-fixed-dim: #EFB8C8;
      --md-sys-color-on-tertiary-fixed: #31111D;
      --md-sys-color-on-tertiary-fixed-variant: #633B48;
      --md-sys-color-error: #F2B8B5;
      --md-sys-color-on-error: #601410;
      --md-sys-color-error-container: #8C1D18;
      --md-sys-color-on-error-container: #F9DEDC;
      --md-sys-color-surface: #141218;
      --md-sys-color-on-surface: #E6E0E9;
      --md-sys-color-surface-variant: #49454F;
      --md-sys-color-on-surface-variant: #CAC4D0;
      --md-sys-color-surface-dim: #141218;
      --md-sys-color-surface-bright: #3B383E;
      --md-sys-color-surface-container-lowest: #0F0D13;
      --md-sys-color-surface-container-low: #1D1B20;
      --md-sys-color-surface-container: #211F26;
      --md-sys-color-surface-container-high: #2B2930;
      --md-sys-color-surface-container-highest: #36343B;
      --md-sys-color-outline: #938F99;
      --md-sys-color-outline-variant: #49454F;
      --md-sys-color-inverse-surface: #E6E0E9;
      --md-sys-color-inverse-on-surface: #313033;
      --md-sys-color-inverse-primary: #4F378B;
      --md-sys-color-scrim: #000000;
      --md-sys-color-shadow: #000000;
    }
  }
  html, body {
    height: 100%;
    margin: 0;
    padding: 0;
    /* Keep the app fixed to the viewport: when the mobile keyboard opens the
       browser must not pan the page; the flexible input area shrinks instead. */
    overflow: hidden;
    overscroll-behavior: none;
    background-color: var(--md-sys-color-surface-container, #f3edf7);
    color: var(--md-sys-color-on-surface, #1d1b20);
    font-family: system-ui, -apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
    transition: background-color 0.3s, color 0.3s;
  }
  .app-container {
    display: flex;
    flex-direction: column;
    /* --app-height tracks visualViewport.height (set from JS) so the layout
       fits above the keyboard on both Android (resizes-content) and iOS. */
    height: var(--app-height, 100dvh);
    padding: 16px;
    box-sizing: border-box;
    gap: 12px;
  }
  .btn-row {
    display: flex;
    gap: 12px;
    flex-shrink: 0;
    align-items: center;
  }
  .btn-row m3e-button {
    flex: 1;
  }
  /* Expressive send button: amplify the built-in press shape-morph so the
     pill visibly squishes (spring physics come from the component). */
  .btn-row m3e-button#btn {
    --m3e-button-shape-pressed-morph: 16px;
  }
  /* Success feedback: the icon flies out of the clipped wrapper and the new
     one flies back in. */
  @keyframes btn-icon-out {
    to { transform: translateX(130%); opacity: 0; }
  }
  @keyframes btn-icon-in {
    from { transform: translateX(-130%); opacity: 0; }
    to { transform: translateX(0); opacity: 1; }
  }
  #btn > m3e-icon.fly-out { animation: btn-icon-out 0.18s ease-in forwards; }
  #btn > m3e-icon.fly-in { animation: btn-icon-in 0.26s cubic-bezier(0.2, 0, 0, 1); }
  @media (prefers-reduced-motion: reduce) {
    #btn > m3e-icon.fly-out, #btn > m3e-icon.fly-in { animation: none; }
  }
  .input-field {
    flex: 1;
    display: flex;
    min-height: 96px;
    position: relative;
    overflow: visible;
  }
  /* Hand-styled M3 outlined field: m3e-form-field's floating label does not
     track multiline textareas, so the box, border notch and textarea are
     styled here directly. The height chain stays unbroken so the field
     shrinks correctly when the mobile keyboard opens. */
  .field-box {
    position: relative;
    flex: 1;
    display: flex;
    min-height: 0;
    border: 1px solid var(--md-sys-color-outline, #79747e);
    border-radius: 12px;
    transition: border-color 0.2s;
  }
  .field-box:focus-within {
    border-color: var(--md-sys-color-primary, #6750a4);
    box-shadow: inset 0 0 0 1px var(--md-sys-color-primary, #6750a4);
  }
  .field-box .flt-label {
    position: absolute;
    top: -9px;
    left: 12px;
    max-width: calc(100% - 28px);
    padding: 0 6px;
    background: var(--md-sys-color-surface-container, #f3edf7);
    color: var(--md-sys-color-on-surface-variant, #49454f);
    font-size: 12px;
    line-height: 18px;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    pointer-events: none;
    z-index: 1;
  }
  .field-box:focus-within .flt-label {
    color: var(--md-sys-color-primary, #6750a4);
  }
  .field-box textarea {
    flex: 1;
    width: 100%;
    height: 100%;
    min-height: 0;
    resize: none;
    border: none;
    outline: none;
    background: transparent;
    color: var(--md-sys-color-on-surface, #1d1b20);
    caret-color: var(--md-sys-color-primary, #6750a4);
    padding: 12px 16px;
    font-family: inherit;
    font-size: 16px;
    line-height: 1.5;
    box-sizing: border-box;
  }
  .nav-row {
    display: flex;
    align-items: center;
    gap: 8px;
    flex-shrink: 0;
    padding: 8px 0;
  }
  .nav-center {
    flex: 1;
    display: flex;
    flex-direction: row;
    align-items: center;
    justify-content: center;
    gap: 6px;
  }
  .nav-mid {
    display: flex;
    align-items: center;
    gap: 6px;
  }
  .nav-info {
    font-size: 0.9rem;
    color: var(--md-sys-color-on-surface-variant, #49454f);
    line-height: 1;
    min-width: 40px;
    text-align: center;
  }
  m3e-button[disabled], m3e-icon-button[disabled] {
    opacity: 0.38;
    pointer-events: none;
  }
  .autostart-row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    flex-shrink: 0;
    gap: 8px;
    padding: 4px 0;
  }
  .autostart-label {
    font-size: 14px;
    color: var(--md-sys-color-on-surface, #444);
    flex: 1 1 auto;
    min-width: 0;
  }
  /* Bottom sheet content */
  .sheet-header {
    font-size: 16px;
    font-weight: 500;
    color: var(--md-sys-color-on-surface, #1d1b20);
    padding: 4px 16px 0;
  }
  .sheet-body {
    display: flex;
    flex-direction: column;
    gap: 4px;
    padding: 8px 16px 20px;
  }
</style>
</head>
<body>
<div class="app-container">
  <div class="btn-row">
    <m3e-button id="btn" variant="filled" size="large">
      <m3e-icon slot="icon" name="send" variant="outlined"></m3e-icon><span class="btn-label">SEND</span>
    </m3e-button>
    <m3e-icon-button id="clear-btn" variant="standard">
      <m3e-icon name="delete" variant="outlined"></m3e-icon>
    </m3e-icon-button>
    <m3e-icon-button id="settings-btn" variant="standard">
      <m3e-icon name="tune" variant="outlined"></m3e-icon>
    </m3e-icon-button>
    <m3e-icon-button id="lang-btn" variant="standard">
      <m3e-icon name="language" variant="outlined"></m3e-icon>
    </m3e-icon-button>
  </div>

  <div class="input-field">
    <div class="field-box">
      <label class="flt-label" for="txt">__LABEL_TYPE_HERE__</label>
      <textarea id="txt" rows="4" autofocus></textarea>
    </div>
  </div>

  <div class="nav-row">
    <m3e-icon-button id="nav-left" variant="standard" disabled>
      <m3e-icon name="chevron_left" variant="outlined"></m3e-icon>
    </m3e-icon-button>
    <div class="nav-center">
      <div class="nav-mid">
        <div class="nav-info" id="nav-info"></div>
      </div>
    </div>
    <m3e-icon-button id="nav-right" variant="standard" disabled>
      <m3e-icon name="chevron_right" variant="outlined"></m3e-icon>
    </m3e-icon-button>
  </div>
</div>

<!-- Settings live in a modal bottom sheet (drag handle, swipe to dismiss,
     fit-to-content height) instead of occupying rows in the main layout. -->
<m3e-bottom-sheet id="settings-sheet" modal handle hideable detents="fit">
  <div slot="header" class="sheet-header" data-i18n="settings_title">设置</div>
  <div class="sheet-body">
    <div class="autostart-row">
      <span class="autostart-label" data-i18n="autostart_label">开机自启（登录后自动弹终端显示二维码）</span>
      <m3e-switch id="autostart-switch"></m3e-switch>
    </div>

    <div class="autostart-row">
      <span class="autostart-label" data-i18n="enter_label">发送后自动按 Enter</span>
      <m3e-switch id="enter-switch"></m3e-switch>
    </div>

    <div class="autostart-row">
      <span class="autostart-label" data-i18n="paste_key_label">粘贴快捷键使用 Ctrl+Shift+V（默认 Ctrl+V）</span>
      <m3e-switch id="paste-key-switch"></m3e-switch>
    </div>
  </div>
</m3e-bottom-sheet>

<!-- Material 3 Expressive (@m3e/web) -->
<!-- m3e builds on Lit + tslib + its own core; the dist files use bare specifiers,
     so we publish an import map before the module script loads. -->
<script type="importmap">
{
  "imports": {
    "lit": "https://unpkg.com/lit@3.3.3/index.js",
    "lit/": "https://unpkg.com/lit@3.3.3/",
    "lit-element": "https://unpkg.com/lit-element@4.2.2/lit-element.js",
    "lit-element/": "https://unpkg.com/lit-element@4.2.2/",
    "lit-html": "https://unpkg.com/lit-html@3.3.3/lit-html.js",
    "lit-html/": "https://unpkg.com/lit-html@3.3.3/",
    "@lit/reactive-element": "https://unpkg.com/@lit/reactive-element@2.1.2/reactive-element.js",
    "@lit/reactive-element/": "https://unpkg.com/@lit/reactive-element@2.1.2/",
    "tslib": "https://unpkg.com/tslib@2.8.1/tslib.es6.js",
    "@m3e/web/core": "https://unpkg.com/@m3e/web@2.7.9/dist/core.min.js",
    "@m3e/web/core/a11y": "https://unpkg.com/@m3e/web@2.7.9/dist/core-a11y.min.js",
    "@m3e/web/core/bidi": "https://unpkg.com/@m3e/web@2.7.9/dist/core-bidi.min.js",
    "@m3e/web/button": "https://unpkg.com/@m3e/web@2.7.9/dist/button.min.js",
    "@m3e/web/icon-button": "https://unpkg.com/@m3e/web@2.7.9/dist/icon-button.min.js"
  }
}
</script>
<!-- One ES module: load m3e, then wait until every custom element is upgraded
     before touching the DOM. This avoids race conditions where page logic runs
     against un-upgraded <m3e-*> elements. -->
<script type="module">
  try {
    await import('https://unpkg.com/@m3e/web@2.7.9/dist/core.min.js');
    await import('https://unpkg.com/@m3e/web@2.7.9/dist/icon.min.js');
    await import('https://unpkg.com/@m3e/web@2.7.9/dist/button.min.js');
    await import('https://unpkg.com/@m3e/web@2.7.9/dist/icon-button.min.js');
    await import('https://unpkg.com/@m3e/web@2.7.9/dist/switch.min.js');
    await import('https://unpkg.com/@m3e/web@2.7.9/dist/snackbar.min.js');
    await import('https://unpkg.com/@m3e/web@2.7.9/dist/bottom-sheet.min.js');
  } catch (err) {
    // Surface CDN/boot failures visibly instead of leaving an unstyled, dead page.
    window.__M3E_BOOT_ERROR__ = String((err && err.message) || err);
    const banner = document.createElement('div');
    banner.textContent = 'Failed to load UI components: ' + window.__M3E_BOOT_ERROR__;
    banner.style.cssText = 'position:fixed;left:16px;right:16px;bottom:16px;background:#b3261e;color:#fff;'
      + 'padding:12px 16px;border-radius:12px;z-index:9999;font:14px/1.4 system-ui,sans-serif';
    document.body.appendChild(banner);
    throw err;
  }

  // Make sure every <m3e-*> element on the DOM has finished upgrading
  // before the rest of this script runs.
  await Promise.all([
    customElements.whenDefined('m3e-button'),
    customElements.whenDefined('m3e-icon-button'),
    customElements.whenDefined('m3e-switch'),
    customElements.whenDefined('m3e-icon'),
    customElements.whenDefined('m3e-snackbar'),
    customElements.whenDefined('m3e-bottom-sheet'),
  ]);

  /* --- Mobile keyboard fit -------------------------------------------------
     When the virtual keyboard opens, keep the layout fitted to the visible
     area and stop the browser from panning the whole page upward (which
     made the textarea text and its floating label appear shifted). */
  const vv = window.visualViewport;
  if (vv) {
    // Clamp to innerHeight too: visualViewport can lag behind window resizes
    // (rotation, devtools), which would push bottom controls out of reach.
    const fitViewport = () => {
      const h = Math.round(Math.min(vv.height, window.innerHeight));
      document.documentElement.style.setProperty('--app-height', h + 'px');
      if (window.scrollY !== 0) window.scrollTo(0, 0);
    };
    vv.addEventListener('resize', fitViewport);
    vv.addEventListener('scroll', fitViewport);
    window.addEventListener('resize', fitViewport);
    fitViewport();
  }

const CONFIG = __CONFIG__;

/* --- i18n (Chinese / English) --- */
const I18N = {
  en: {
    title: "Input",
    label_type_here: "Type here...",
    autostart_label: "Auto-start on login (opens terminal with QR code)",
    sent: "Sent!",
    error_status: "Error ",
    network_error: "Network error",
    sending: "Sending...",
    offline: "Offline",
    send: "SEND",
    autostart_on: "Auto-start enabled",
    autostart_off: "Auto-start disabled",
    autostart_fail: "Failed: ",
    autostart_err: "Error: ",
    autostart_neterr: "Network error",
    enter_label: "Auto press Enter after send",
    enter_on: "Auto-Enter enabled",
    enter_off: "Auto-Enter disabled",
    paste_key_label: "Paste with Ctrl+Shift+V (default Ctrl+V)",
    paste_key_on: "Using Ctrl+Shift+V",
    paste_key_off: "Using Ctrl+V",
    settings_title: "Settings",
    clear_label: "Clear text",
    lang_label: "Switch language",
    prev_label: "Previous entry",
    next_label: "Next entry",
  },
  zh: {
    title: "输入",
    label_type_here: "在此输入…",
    autostart_label: "开机自启（登录后自动弹终端显示二维码）",
    sent: "已发送！",
    error_status: "错误 ",
    network_error: "网络错误",
    sending: "发送中…",
    offline: "离线",
    send: "发送",
    autostart_on: "已开启开机自启",
    autostart_off: "已关闭开机自启",
    autostart_fail: "失败: ",
    autostart_err: "错误: ",
    autostart_neterr: "网络错误",
    enter_label: "发送后自动按 Enter",
    enter_on: "已开启自动 Enter",
    enter_off: "已关闭自动 Enter",
    paste_key_label: "粘贴快捷键使用 Ctrl+Shift+V（默认 Ctrl+V）",
    paste_key_on: "已切换为 Ctrl+Shift+V",
    paste_key_off: "已恢复 Ctrl+V",
    settings_title: "设置",
    clear_label: "清除文本",
    lang_label: "切换语言",
    prev_label: "上一条",
    next_label: "下一条",
  },
};

const LANG_STORAGE_KEY = "input-from-web-lang";

function detectLang() {
  // 1. ?lang= override (also saved for next visit)
  const fromUrl = new URLSearchParams(location.search).get("lang");
  if (fromUrl === "zh" || fromUrl === "en") {
    localStorage.setItem(LANG_STORAGE_KEY, fromUrl);
    return fromUrl;
  }
  // 2. saved preference
  const saved = localStorage.getItem(LANG_STORAGE_KEY);
  if (saved === "zh" || saved === "en") return saved;
  // 3. auto from browser
  const nav = (navigator.language || "en").toLowerCase();
  return nav.startsWith("zh") ? "zh" : "en";
}

let LANG = detectLang();
function t(key) {
  const dict = I18N[LANG] || I18N.en;
  return dict[key] !== undefined ? dict[key] : (I18N.en[key] || key);
}

function applyStaticI18n() {
  document.documentElement.lang = LANG;
  document.title = t("title");
  // The textarea label lives on the hand-styled outlined field box.
  const label = document.querySelector('.field-box .flt-label');
  if (label) label.textContent = t("label_type_here");
  document.querySelectorAll('[data-i18n]').forEach(el => {
    el.textContent = t(el.getAttribute('data-i18n'));
  });
  // Accessible names for the icon-only buttons.
  const ariaMap = [
    ["settings-btn", "settings_title"],
    ["clear-btn", "clear_label"],
    ["lang-btn", "lang_label"],
    ["nav-left", "prev_label"],
    ["nav-right", "next_label"],
  ];
  for (const [id, key] of ariaMap) {
    const el = document.getElementById(id);
    if (el) el.setAttribute("aria-label", t(key));
  }
}

/* --- Token: URL query > localStorage > null --- */
const STORAGE_KEY = "input-from-web-token";
let token = new URLSearchParams(location.search).get("token");
if (token) {
  localStorage.setItem(STORAGE_KEY, token);
} else {
  token = localStorage.getItem(STORAGE_KEY);
}

const txt = document.getElementById("txt");
const btn = document.getElementById("btn");
const btnLabel = btn.querySelector(".btn-label");
const btnIcon = btn.querySelector('m3e-icon[slot="icon"]');
const clearBtn = document.getElementById("clear-btn");
const navLeft = document.getElementById("nav-left");
const navRight = document.getElementById("nav-right");
const navInfo = document.getElementById("nav-info");

// m3e-button has no `icon` JS property — update the slotted <m3e-icon>'s `name` instead.
function setBtnIcon(name) {
  if (btnIcon) btnIcon.setAttribute("name", name);
}

// Expressive swap: current icon flies out (clipped by the button wrapper),
// then the new icon flies in. Falls back to an instant swap without motion.
function setBtnIconAnimated(name) {
  if (!btnIcon || matchMedia("(prefers-reduced-motion: reduce)").matches) {
    setBtnIcon(name);
    return;
  }
  btnIcon.classList.remove("fly-in", "fly-out");
  // Force a style flush so re-adding the class restarts the animation.
  void btnIcon.offsetWidth;
  btnIcon.classList.add("fly-out");
  btnIcon.addEventListener("animationend", () => {
    setBtnIcon(name);
    btnIcon.classList.remove("fly-out");
    void btnIcon.offsetWidth;
    btnIcon.classList.add("fly-in");
  }, { once: true });
}

btn.addEventListener("click", doSend);
clearBtn.addEventListener("click", clearText);
navLeft.addEventListener("click", histBack);
navRight.addEventListener("click", histForward);

/* --- History --- */
const history = [];
let histIdx = 0;
let draft = "";

function updateNav() {
  navLeft.disabled = (histIdx === 0 && history.length === 0) || histIdx === 0;
  navRight.disabled = histIdx >= history.length;
  if (history.length > 0) {
    const pos = histIdx < history.length ? histIdx + 1 : history.length + 1;
    navInfo.textContent = pos + " / " + (history.length + 1);
  } else {
    navInfo.textContent = "";
  }
}

function histBack() {
  if (histIdx <= 0) return;
  if (histIdx === history.length) draft = txt.value;
  histIdx--;
  txt.value = history[histIdx];
  txt.focus();
  updateNav();
}

function histForward() {
  if (histIdx >= history.length) return;
  histIdx++;
  txt.value = histIdx < history.length ? history[histIdx] : draft;
  txt.focus();
  updateNav();
}

updateNav();

/* --- Substitutions --- */
function escapeRegex(s) {
  return s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

const subEntries = Object.entries(CONFIG.substitutions || {})
  .sort((a, b) => b[0].length - a[0].length);

function applySubstitutions() {
  let text = txt.value;
  let changed = false;
  for (const [phrase, replacement] of subEntries) {
    const re = new RegExp("(^|\\s)" + escapeRegex(phrase) + "(?=\\s|$)", "gi");
    if (re.test(text)) {
      text = text.replace(re, function(m, before) { return before + replacement; });
      changed = true;
    }
  }
  if (changed) {
    const pos = txt.selectionStart;
    const diff = txt.value.length - text.length;
    txt.value = text;
    txt.selectionStart = txt.selectionEnd = Math.max(0, pos - diff);
  }
}

/* --- Voice send --- */
let voiceTimer = null;

function checkVoiceCommand() {
  const vs = CONFIG.voice_send;
  if (!vs || !vs.enabled) return;
  if (voiceTimer) { clearTimeout(voiceTimer); voiceTimer = null; }

  const text = txt.value.trimEnd();
  if (!text) return;

  const words = text.split(/\s+/);
  const lastWord = words[words.length - 1].toLowerCase();

  const sendWords = (vs.send_words || []).map(w => w.toLowerCase());
  const clearWords = (vs.clear_words || []).map(w => w.toLowerCase());

  let action = null;
  if (sendWords.includes(lastWord)) action = "send";
  else if (clearWords.includes(lastWord)) action = "clear";

  if (action) {
    const delay = (vs.delay_seconds || 1.5) * 1000;
    voiceTimer = setTimeout(() => {
      voiceTimer = null;
      const re = new RegExp("\\s*" + escapeRegex(lastWord) + "\\s*$", "i");
      txt.value = txt.value.replace(re, "");
      if (action === "send") doSend();
      else clearText();
    }, delay);
  }
}

txt.addEventListener("input", () => {
  applySubstitutions();
  checkVoiceCommand();
});

/* --- Actions --- */

function clearText() {
  txt.value = "";
  txt.focus();
}

async function doSend() {
  const text = txt.value;
  if (!text) return;
  isSending = true;
  updateButtonState();
  try {
    const res = await fetch("/send?token=" + encodeURIComponent(token), {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({text: text})
    });
    if (res.ok) {
      history.push(text);
      histIdx = history.length;
      draft = "";
      txt.value = "";
      updateNav();
      setBtnIconAnimated("check");
      if (btnLabel) btnLabel.textContent = t("sent");
      setTimeout(() => {
        isSending = false;
        updateButtonState();
      }, 800);
      txt.focus();
    } else {
      setBtnIcon("error");
      if (btnLabel) btnLabel.textContent = t("error_status") + res.status;
      setTimeout(() => {
        isSending = false;
        updateButtonState();
      }, 2000);
    }
  } catch(e) {
    setBtnIcon("error");
    if (btnLabel) btnLabel.textContent = t("network_error");
    setTimeout(() => {
      isSending = false;
      updateButtonState();
    }, 2000);
  }
}

/* --- Connection State --- */
let isConnected = false;
let isSending = false;

function updateButtonState() {
  if (isSending) {
    btn.disabled = true;
    setBtnIcon("hourglass_empty");
    if (btnLabel) btnLabel.textContent = t("sending");
  } else if (!isConnected) {
    btn.disabled = true;
    setBtnIcon("wifi_off");
    if (btnLabel) btnLabel.textContent = t("offline");
  } else {
    btn.disabled = false;
    setBtnIcon("send");
    if (btnLabel) btnLabel.textContent = t("send");
  }
}

setInterval(async () => {
  try {
    const r = await fetch("/ping", {signal: AbortSignal.timeout(3000)});
    isConnected = r.ok;
  } catch(e) {
    isConnected = false;
  }
  updateButtonState();
}, 1000);

updateButtonState();

/* --- Autostart toggle --- */
const autostartSwitch = document.getElementById("autostart-switch");

async function refreshAutostart() {
  try {
    const r = await fetch("/autostart?token=" + encodeURIComponent(token));
    if (r.ok) {
      const data = await r.json();
      autostartSwitch.checked = !!data.installed;
    }
  } catch (e) { /* ignore */ }
}

autostartSwitch.addEventListener("change", async () => {
  const want = autostartSwitch.checked;
  const action = want ? "install" : "uninstall";
  autostartSwitch.disabled = true;
  try {
    const r = await fetch("/autostart?token=" + encodeURIComponent(token), {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({action: action}),
    });
    if (r.ok) {
      const data = await r.json();
      if (data.ok) {
        window.M3eSnackbar.open(want ? t("autostart_on") : t("autostart_off"));
      } else {
        autostartSwitch.checked = !want;
        window.M3eSnackbar.open(t("autostart_fail") + (data.message || ""));
      }
    } else {
      autostartSwitch.checked = !want;
      window.M3eSnackbar.open(t("autostart_err") + r.status);
    }
  } catch (e) {
    autostartSwitch.checked = !want;
    window.M3eSnackbar.open(t("autostart_neterr"));
  } finally {
    autostartSwitch.disabled = false;
  }
});

refreshAutostart();

/* --- Auto-press-Enter toggle --- */
const enterSwitch = document.getElementById("enter-switch");

async function refreshEnterSwitch() {
  try {
    const r = await fetch("/settings?token=" + encodeURIComponent(token));
    if (r.ok) {
      const data = await r.json();
      enterSwitch.checked = !!data.auto_press_enter;
    }
  } catch (e) { /* ignore */ }
}

enterSwitch.addEventListener("change", async () => {
  const want = enterSwitch.checked;
  enterSwitch.disabled = true;
  try {
    const r = await fetch("/settings?token=" + encodeURIComponent(token), {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({auto_press_enter: want}),
    });
    if (r.ok) {
      window.M3eSnackbar.open(want ? t("enter_on") : t("enter_off"));
    } else {
      enterSwitch.checked = !want;
      window.M3eSnackbar.open(t("autostart_err") + r.status);
    }
  } catch (e) {
    enterSwitch.checked = !want;
    window.M3eSnackbar.open(t("autostart_neterr"));
  } finally {
    enterSwitch.disabled = false;
  }
});

refreshEnterSwitch();

/* --- Paste key toggle (Ctrl+V ⇄ Ctrl+Shift+V) --- */
const pasteKeySwitch = document.getElementById("paste-key-switch");

async function refreshPasteKeySwitch() {
  try {
    const r = await fetch("/settings?token=" + encodeURIComponent(token));
    if (r.ok) {
      const data = await r.json();
      pasteKeySwitch.checked = data.paste_key === "ctrl+shift+v";
    }
  } catch (e) { /* ignore */ }
}

pasteKeySwitch.addEventListener("change", async () => {
  const want = pasteKeySwitch.checked ? "ctrl+shift+v" : "ctrl+v";
  pasteKeySwitch.disabled = true;
  try {
    const r = await fetch("/settings?token=" + encodeURIComponent(token), {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({paste_key: want}),
    });
    if (r.ok) {
      const data = await r.json().catch(() => ({}));
      if (data.error) {
        pasteKeySwitch.checked = !pasteKeySwitch.checked;
        window.M3eSnackbar.open(t("autostart_err") + data.error);
      } else {
        window.M3eSnackbar.open(want === "ctrl+shift+v" ? t("paste_key_on") : t("paste_key_off"));
      }
    } else {
      pasteKeySwitch.checked = !pasteKeySwitch.checked;
      window.M3eSnackbar.open(t("autostart_err") + r.status);
    }
  } catch (e) {
    pasteKeySwitch.checked = !pasteKeySwitch.checked;
    window.M3eSnackbar.open(t("autostart_neterr"));
  } finally {
    pasteKeySwitch.disabled = false;
  }
});

refreshPasteKeySwitch();

/* --- Settings bottom sheet --- */
const settingsBtn = document.getElementById("settings-btn");
const settingsSheet = document.getElementById("settings-sheet");
settingsBtn.addEventListener("click", () => settingsSheet.show());

/* --- Language switch --- */
const langBtn = document.getElementById("lang-btn");
langBtn.addEventListener("click", () => {
  LANG = (LANG === "zh") ? "en" : "zh";
  localStorage.setItem(LANG_STORAGE_KEY, LANG);
  applyStaticI18n();
  updateButtonState();
});

applyStaticI18n();
updateButtonState();

if ("serviceWorker" in navigator) {
  navigator.serviceWorker.register("/sw.js");
}
</script>
</body>
</html>
"""


def get_lan_ip():
    """Get LAN IP via UDP socket trick (no traffic actually sent)."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    finally:
        s.close()


def _is_ascii(text: str) -> bool:
    try:
        text.encode("ascii")
    except UnicodeEncodeError:
        return False
    return True


def inject_text(text):
    """Inject text using the chosen method."""
    if METHOD == "type" and _is_ascii(text):
        subprocess.run(
            ["ydotool", "type", "--key-delay", "0", "--", text],
            check=True,
            timeout=30,
        )
    else:
        subprocess.run(
            ["wl-copy", "--", text],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=True,
            timeout=5,
        )
        time.sleep(0.1)
        # When method is "type" but text is non-ASCII, we fell back to clipboard.
        # Auto-paste is required since the user expected direct typing.
        # When method is "clipboard", respect the AUTO_PASTE setting.
        if AUTO_PASTE or (METHOD == "type" and not _is_ascii(text)):
            # Build the paste chord: Ctrl+V (29,47) or Ctrl+Shift+V (42,29,47).
            # Key release order is the reverse of press order.
            # 29=Ctrl, 42=Shift, 47=V (Linux x86 keycodes).
            if PASTE_KEY == "ctrl+shift+v":
                # Press: Shift, Ctrl, V  →  Release: V, Ctrl, Shift
                chord = ["42:1", "29:1", "47:1", "47:0", "29:0", "42:0"]
            else:
                # Default: Ctrl+V →  Release: V, Ctrl
                chord = ["29:1", "47:1", "47:0", "29:0"]
            subprocess.run(
                ["ydotool", "key", "-d", "100", *chord],
                check=True,
                timeout=5,
            )

    # Independently of auto_paste: optionally press Enter after the text
    # has been typed / pasted. Useful for chat boxes, messengers, shells.
    if AUTO_PRESS_ENTER:
        subprocess.run(
            ["ydotool", "key", "-d", "50", "28:1", "28:0"],  # 28 = Return
            check=True,
            timeout=5,
        )


def check_token():
    if USE_TOKEN and request.args.get("token") != TOKEN:
        abort(403)


@app.route("/ping")
def ping():
    return {"ok": True}


@app.route("/manifest.json")
def manifest():
    return {
        "name": "Input from Web",
        "short_name": "Input",
        "start_url": "/",
        "display": "standalone",
        "background_color": "#1a1a1a",
        "theme_color": "#1a1a1a",
        "icons": [{"src": "/icon.svg", "sizes": "512x512", "type": "image/svg+xml"}],
    }


@app.route("/icon.svg")
def icon():
    return send_from_directory(SCRIPT_DIR, "icon.svg", mimetype="image/svg+xml")


@app.route("/sw.js")
def service_worker():
    return Response(
        'self.addEventListener("fetch", e => e.respondWith(fetch(e.request)));',
        mimetype="application/javascript",
    )


@app.route("/")
def index():
    # Page is always served — token security is on POST /send.
    # Client gets token from URL query (first visit) or localStorage (PWA / bookmark).
    profile_json = json.dumps(PROFILE, ensure_ascii=False)

    # Determine initial UI language: ?lang= override > Accept-Language > en
    lang_override = request.args.get("lang", "").lower()
    if lang_override in ("zh", "en"):
        ui_lang = lang_override
    else:
        accept = request.headers.get("Accept-Language", "")
        ui_lang = "zh" if accept.lower().startswith("zh") else "en"
    ui_title = "输入" if ui_lang == "zh" else "Input"
    ui_label = "在此输入…" if ui_lang == "zh" else "Type here..."

    html = (HTML_TEMPLATE
            .replace("__CONFIG__", profile_json)
            .replace("__LANG__", ui_lang)
            .replace("__TITLE__", ui_title)
            .replace("__LABEL_TYPE_HERE__", ui_label))
    return html


@app.route("/send", methods=["POST"])
def send():
    check_token()
    data = request.get_json(force=True)
    text = data.get("text", "")
    if not text:
        return {"error": "empty"}, 400
    try:
        inject_text(text)
    except subprocess.CalledProcessError as e:
        print(f"Injection failed: {e}", file=sys.stderr)
        return {"error": "injection failed"}, 500
    return {"ok": True}


@app.route("/autostart", methods=["GET", "POST"])
def autostart():
    # Protected by the security token, like /send.
    check_token()
    if request.method == "GET":
        return {"installed": autostart_installed()}
    action = (request.get_json(force=True, silent=True) or {}).get("action")
    if action == "install":
        ok, msg = install_autostart()
        return {"ok": ok, "message": msg}
    elif action == "uninstall":
        ok, msg = uninstall_autostart()
        return {"ok": ok, "message": msg}
    return {"error": "unknown action"}, 400


@app.route("/settings", methods=["GET", "POST"])
def settings():
    """Read or update profile-level toggles. Token-protected, like /send."""
    global PROFILE, AUTO_PRESS_ENTER, PASTE_KEY, FULL_CONFIG
    check_token()
    if request.method == "GET":
        return {
            "auto_press_enter": AUTO_PRESS_ENTER,
            "paste_key": PASTE_KEY,
        }
    data = request.get_json(force=True, silent=True) or {}
    dirty = False
    if "auto_press_enter" in data:
        AUTO_PRESS_ENTER = bool(data["auto_press_enter"])
        PROFILE["auto_press_enter"] = AUTO_PRESS_ENTER
        dirty = True
    if "paste_key" in data:
        requested = str(data["paste_key"]).strip().lower()
        if requested in ("ctrl+v", "ctrl+shift+v"):
            PASTE_KEY = requested
            PROFILE["paste_key"] = PASTE_KEY
            dirty = True
        else:
            return {"error": "paste_key must be 'ctrl+v' or 'ctrl+shift+v'"}, 400
    if dirty and FULL_CONFIG is not None and CURRENT_PROFILE_NAME in FULL_CONFIG.get("profiles", {}):
        FULL_CONFIG["profiles"][CURRENT_PROFILE_NAME] = PROFILE
        try:
            save_config(FULL_CONFIG)
        except OSError as e:
            print(f"Failed to persist settings: {e}", file=sys.stderr)
    return {
        "ok": True,
        "auto_press_enter": AUTO_PRESS_ENTER,
        "paste_key": PASTE_KEY,
    }


def main():
    global METHOD, USE_TOKEN, PERMANENT_LINK, AUTO_PASTE, PASTE_KEY, AUTO_PRESS_ENTER
    global TOKEN, PROFILE, FULL_CONFIG, CURRENT_PROFILE_NAME
    parser = argparse.ArgumentParser(description="Type on your phone, paste on your desktop.")
    parser.add_argument("--method", choices=["clipboard", "type"], default=None,
                        help="Override profile method. type: ydotool type. clipboard: wl-copy only.")
    parser.add_argument("--port", type=int, default=None,
                        help="Override profile port (default: 5123)")
    parser.add_argument("--profile", default=None,
                        help="Config profile name (default: from config file)")
    parser.add_argument("--permanent-link", action="store_true",
                        help="Reuse a stored token across sessions. "
                             "QR shows a clean URL; phone remembers the token.")
    parser.add_argument("--permanent-link-refresh", action="store_true",
                        help="Replace the stored permanent token with a new one. "
                             "Implies --permanent-link.")
    parser.add_argument("--install-autostart", action="store_true",
                        help="Install a user autostart entry (opens a terminal with the "
                             "QR code on login). Detects the available terminal emulator.")
    parser.add_argument("--uninstall-autostart", action="store_true",
                        help="Remove the user autostart entry if present.")
    args = parser.parse_args()

    # One-shot autostart management — exit after performing the action.
    if args.install_autostart or args.uninstall_autostart:
        if args.install_autostart and args.uninstall_autostart:
            print("Error: --install-autostart and --uninstall-autostart are mutually exclusive.",
                  file=sys.stderr)
            sys.exit(1)
        if args.install_autostart:
            ok, msg = install_autostart()
        else:
            ok, msg = uninstall_autostart()
        print(msg)
        sys.exit(0 if ok else 1)

    PROFILE, profile_name, full_config = load_or_create_config(args.profile)
    FULL_CONFIG = full_config
    CURRENT_PROFILE_NAME = profile_name

    # CLI flags override profile, profile overrides built-in defaults
    METHOD = args.method or PROFILE.get("method", "type")
    AUTO_PASTE = PROFILE.get("auto_paste", False)
    PASTE_KEY = PROFILE.get("paste_key", "ctrl+v")
    AUTO_PRESS_ENTER = PROFILE.get("auto_press_enter", False)
    USE_TOKEN = PROFILE.get("use_security_token", True)
    PERMANENT_LINK = args.permanent_link or args.permanent_link_refresh

    # Permanent link: reuse or generate+store a token in the config
    permanent_is_new = False
    if PERMANENT_LINK and USE_TOKEN:
        stored = PROFILE.get("permanent_token")
        if args.permanent_link_refresh and stored:
            print("  Replacing permanent token with a new one.")
            stored = None
        if stored:
            TOKEN = stored
            print("  Using permanent token from config.")
        else:
            permanent_is_new = True
            PROFILE["permanent_token"] = TOKEN
            full_config["profiles"][profile_name] = PROFILE
            save_config(full_config)
            print("  Generated and saved permanent token to config.")

    if not USE_TOKEN:
        print("\n\033[1;97;41m  WARNING: security token is DISABLED  \033[0m")
        print("\033[1;31m  Anyone on your network can send keystrokes to this machine!\033[0m")
        print("\033[1;31m  Only run this way on a trusted private network.\033[0m\n")

    host = get_lan_ip()
    port = args.port or PROFILE.get("port", 5123)

    base_url = f"http://{host}:{port}/"
    token_url = f"{base_url}?token={TOKEN}" if USE_TOKEN else base_url

    if PERMANENT_LINK and USE_TOKEN:
        if permanent_is_new:
            # First setup or refresh: QR includes token so phone can save it
            qr_url = token_url
            print(f"\n  First-time setup (scan QR): {token_url}")
            print(f"  Bookmark URL (next time):   {base_url}\n")
        else:
            # Reusing stored token: QR is clean, phone already has token
            qr_url = base_url
            print(f"\n  QR URL (bookmark): {base_url}")
            print(f"  Setup URL:         {token_url}\n")
    else:
        qr_url = token_url
        print(f"\n  URL: {token_url}\n")

    qr = qrcode.QRCode(box_size=1, border=1)
    qr.add_data(qr_url)
    qr.make(fit=True)
    qr.print_ascii(invert=True)
    print()

    app.run(host=host, port=port, debug=False)


if __name__ == "__main__":
    main()
