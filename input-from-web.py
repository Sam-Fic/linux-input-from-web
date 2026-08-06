#!/usr/bin/env python3
"""input-from-web: Type on your phone, inject into focused desktop app."""

import argparse
import json
import os
import secrets
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
PROFILE = {}

CONFIG_PATH = os.path.expanduser("~/.input-from-web-conf.json")

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
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, interactive-widget=resizes-content">
<meta name="theme-color" content="#6750A4">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<link rel="manifest" href="/manifest.json">
<link rel="icon" href="/icon.png">
<link rel="apple-touch-icon" href="/icon.png">
<title>Input</title>

<!-- Material Design 3 (mdui) Fonts & CSS -->
<link href="https://fonts.googleapis.com/icon?family=Material+Icons" rel="stylesheet">
<link href="https://fonts.googleapis.com/css2?family=Roboto:wght@300;400;500;700&display=swap" rel="stylesheet">
<link rel="stylesheet" href="https://unpkg.com/mdui@2/mdui.css">

<style>
  html, body {
    height: 100%;
    margin: 0;
    padding: 0;
    /* mdui handles background colors via its theme tokens, fallback provided */
    background-color: var(--mdui-color-surface-container, #f3edf7);
    font-family: 'Roboto', sans-serif;
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
  .status {
    font-size: 0.85rem;
    color: var(--mdui-color-primary, #6750A4);
    font-weight: 500;
    min-height: 1.2em;
    line-height: 1;
  }
￼  mdui-button[disabled], mdui-button-icon[disabled] {
    opacity: 0.38;
    pointer-events: none;
  }
</style>
</head>
<body>
<div class="app-container">
  <div class="btn-row">
    <mdui-button id="btn" variant="filled" icon="send">SEND</mdui-button>
    <mdui-button-icon id="clear-btn" icon="delete"></mdui-button-icon>
  </div>

  <div class="input-field">
    <mdui-text-field 
      id="txt" 
      rows="10"
      variant="outlined" 
      label="Type here..." 
      autofocus
    ></mdui-text-field>
  </div>

  <div class="nav-row">
    <mdui-button-icon id="nav-left" icon="chevron_left" disabled></mdui-button-icon>
    <div class="nav-center">
      <div class="nav-mid">
        <div class="nav-info" id="nav-info"></div>
        <div class="status" id="status"></div>
      </div>
    </div>
    <mdui-button-icon id="nav-right" icon="chevron_right" disabled></mdui-button-icon>
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
const statusEl = document.getElementById("status");
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
let statusTimer = null;

function clearText() {
  txt.value = "";
  txt.focus();
  showStatus("");
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
      btn.textContent = "Sent!";
      setTimeout(() => {
        isSending = false;
        updateButtonState();
      }, 800);
      txt.focus();
    } else {
      showStatus("Error: " + res.status);
    }
  } catch(e) {
    showStatus("Network error");
  }
  isSending = false;
  updateButtonState();
}

function showStatus(msg) {
  if (statusTimer) clearTimeout(statusTimer);
  if (msg) {
    statusEl.textContent = msg;
    statusTimer = setTimeout(() => {
      statusEl.textContent = "";
      statusTimer = null;
    }, 2000);
  }
}

/* --- Connection State --- */
let isConnected = false;
let isSending = false;

function updateButtonState() {
  if (isSending) {
    btn.disabled = true;
    btn.icon = "hourglass_empty";
    btn.textContent = "Sending...";
  } else if (!isConnected) {
    btn.disabled = true;
    btn.icon = "wifi_off";
    btn.textContent = "Offline";
  } else {
    btn.disabled = false;
    btn.icon = "send";
    btn.textContent = "SEND";
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
        "icons": [{"src": "/icon.png", "sizes": "512x512", "type": "image/png"}],
    }


@app.route("/icon.png")
def icon():
    return send_from_directory(SCRIPT_DIR, "icon.png", mimetype="image/png")


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
    return HTML_TEMPLATE.replace("__CONFIG__", profile_json)


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


def main():
    global METHOD, USE_TOKEN, PERMANENT_LINK, AUTO_PASTE, TOKEN, PROFILE
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
    args = parser.parse_args()

    PROFILE, profile_name, full_config = load_or_create_config(args.profile)

    # CLI flags override profile, profile overrides built-in defaults
    METHOD = args.method or PROFILE.get("method", "type")
    AUTO_PASTE = PROFILE.get("auto_paste", False)
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
