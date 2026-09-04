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
        "  true  - after wl-copy, simulate Ctrl+V via ydotool (clipboard method only).",
        "  false - clipboard only, you paste manually (default).",
        "  Ignored when method is 'type'. Useful for GUI apps, not terminals.",
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

<!-- Material Design 3 (mdui) Fonts & CSS -->
<link href="https://fonts.googleapis.com/icon?family=Material+Icons" rel="stylesheet">
<link rel="stylesheet" href="https://unpkg.com/mdui@2/mdui.css">

<style>
  html, body {
    height: 100%;
    margin: 0;
    padding: 0;
    /* mdui handles background colors via its theme tokens, fallback provided */
    background-color: var(--mdui-color-surface-container, #f3edf7);
    # font-family: system-ui, -apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
    color: var(--mdui-color-on-surface, #1d1b20);
    transition: background-color 0.3s, color 0.3s;
  }
  .app-container {
    display: flex;
    flex-direction: column;
    height: 100dvh;
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
  .btn-row mdui-button {
    flex: 1;
  }
  .input-field {
    flex: 1;
    display: flex;
    min-height: 150px;
    position: relative;
    overflow: visible;
  }
  .input-field mdui-text-field {
    width: 100%;
    flex: 1;
  }
  /* Target the internal textarea via CSS part for full height */
  .input-field mdui-text-field::part(input) {
    height: 100%;
    max-height: none !important;
    resize: none;
    overflow-y: auto;
  }
  /* Prevent label clipping when floating */
  .input-field mdui-text-field::part(label) {
    z-index: 1;
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
    color: var(--mdui-color-on-surface-variant, #49454f);
    line-height: 1;
    min-width: 40px;
    text-align: center;
  }
  mdui-button[disabled], mdui-button-icon[disabled] {
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
    color: var(--mdui-color-on-surface, #444);
    flex: 1 1 auto;
    min-width: 0;
  }
</style>
</head>
<body>
<div class="app-container">
  <div class="btn-row">
    <mdui-button id="btn" variant="filled" icon="send">SEND</mdui-button>
    <mdui-button-icon id="clear-btn" icon="delete"></mdui-button-icon>
    <mdui-button-icon id="lang-btn" icon="language"></mdui-button-icon>
  </div>

  <div class="input-field">
    <mdui-text-field 
      id="txt" 
      rows="10"
      variant="outlined" 
      label="__LABEL_TYPE_HERE__" 
      autofocus
    ></mdui-text-field>
  </div>

  <div class="nav-row">
    <mdui-button-icon id="nav-left" icon="chevron_left" disabled></mdui-button-icon>
    <div class="nav-center">
      <div class="nav-mid">
        <div class="nav-info" id="nav-info"></div>
      </div>
    </div>
    <mdui-button-icon id="nav-right" icon="chevron_right" disabled></mdui-button-icon>
  </div>

  <div class="autostart-row">
    <span class="autostart-label" data-i18n="autostart_label">开机自启（登录后自动弹终端显示二维码）</span>
    <mdui-switch id="autostart-switch"></mdui-switch>
  </div>

  <div class="autostart-row">
    <span class="autostart-label" data-i18n="enter_label">发送后自动按 Enter</span>
    <mdui-switch id="enter-switch"></mdui-switch>
  </div>
</div>

<!-- Material Design 3 (mdui) JS -->
<script src="https://unpkg.com/mdui@2/mdui.global.js"></script>
<script>
// Apply Material 3 Dynamic Color (Material You)
// #6750A4 is the baseline M3 seed color. mdui automatically extracts and generates 
// the full tonal color palette (Primary, Secondary, Surface, etc.) and handles Dark Mode automatically.
mdui.setColorScheme('#6750A4');

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
  const label = document.querySelector('#txt');
  if (label) label.setAttribute("label", t("label_type_here"));
  document.querySelectorAll('[data-i18n]').forEach(el => {
    el.textContent = t(el.getAttribute('data-i18n'));
  });
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
const clearBtn = document.getElementById("clear-btn");
const navLeft = document.getElementById("nav-left");
const navRight = document.getElementById("nav-right");
const navInfo = document.getElementById("nav-info");

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
      btn.icon = "check";
      btn.textContent = t("sent");
      setTimeout(() => {
        isSending = false;
        updateButtonState();
      }, 800);
      txt.focus();
    } else {
      btn.icon = "error";
      btn.textContent = t("error_status") + res.status;
      setTimeout(() => {
        isSending = false;
        updateButtonState();
      }, 2000);
    }
  } catch(e) {
    btn.icon = "error";
    btn.textContent = t("network_error");
    setTimeout(() => {
      isSending = false;
      updateButtonState();
    }, 2000);
  }
  isSending = false;
  updateButtonState();
}

/* --- Connection State --- */
let isConnected = false;
let isSending = false;

function updateButtonState() {
  if (isSending) {
    btn.disabled = true;
    btn.icon = "hourglass_empty";
    btn.textContent = t("sending");
  } else if (!isConnected) {
    btn.disabled = true;
    btn.icon = "wifi_off";
    btn.textContent = t("offline");
  } else {
    btn.disabled = false;
    btn.icon = "send";
    btn.textContent = t("send");
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
        mdui.snackbar({message: want ? t("autostart_on") : t("autostart_off")});
      } else {
        autostartSwitch.checked = !want;
        mdui.snackbar({message: t("autostart_fail") + (data.message || "")});
      }
    } else {
      autostartSwitch.checked = !want;
      mdui.snackbar({message: t("autostart_err") + r.status});
    }
  } catch (e) {
    autostartSwitch.checked = !want;
    mdui.snackbar({message: t("autostart_neterr")});
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
      mdui.snackbar({message: want ? t("enter_on") : t("enter_off")});
    } else {
      enterSwitch.checked = !want;
      mdui.snackbar({message: t("autostart_err") + r.status});
    }
  } catch (e) {
    enterSwitch.checked = !want;
    mdui.snackbar({message: t("autostart_neterr")});
  } finally {
    enterSwitch.disabled = false;
  }
});

refreshEnterSwitch();

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
            subprocess.run(
                ["ydotool", "key", "-d", "100", "29:1", "47:1", "47:0", "29:0"],
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
    global PROFILE, AUTO_PRESS_ENTER, FULL_CONFIG
    check_token()
    if request.method == "GET":
        return {"auto_press_enter": AUTO_PRESS_ENTER}
    data = request.get_json(force=True, silent=True) or {}
    if "auto_press_enter" in data:
        AUTO_PRESS_ENTER = bool(data["auto_press_enter"])
        PROFILE["auto_press_enter"] = AUTO_PRESS_ENTER
        if FULL_CONFIG is not None and CURRENT_PROFILE_NAME in FULL_CONFIG.get("profiles", {}):
            FULL_CONFIG["profiles"][CURRENT_PROFILE_NAME] = PROFILE
            try:
                save_config(FULL_CONFIG)
            except OSError as e:
                print(f"Failed to persist settings: {e}", file=sys.stderr)
    return {"ok": True, "auto_press_enter": AUTO_PRESS_ENTER}


def main():
    global METHOD, USE_TOKEN, PERMANENT_LINK, AUTO_PASTE, AUTO_PRESS_ENTER
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
