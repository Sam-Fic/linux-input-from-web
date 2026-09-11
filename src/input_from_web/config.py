"""Load and persist ~/.input-from-web-conf.json."""

import json
import os
import sys

from .paths import CONFIG_PATH

DEFAULT_CONFIG = {
    "_comment": [
        "input-from-web configuration file.",
        "",
        "default_profile: which profile to use when --profile is not specified.",
        "",
        "profiles.<name>.method:",
        "  'type'      - simulate keystrokes (ydotool on Linux, SendInput on Windows, AppleScript on macOS). Default.",
        "  'clipboard' - copy to system clipboard (wl-copy on Linux, pbcopy on macOS, Win32 clipboard on Windows);",
        "  Can be overridden with --method on the command line.",
        "",
        "profiles.<name>.auto_paste:",
        "  true  - after copying, simulate a paste keystroke (clipboard method only).",
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
        "  true  - after inject_text, simulate an extra Enter key via the platform injector.",
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
                "send_words": ["send", "发送"],
                "clear_words": ["clear", "清除"],
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
    """Load config from disk, creating default if missing.

    Returns (profile, profile_name, full_config).
    """
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
        print(
            f"Error: profile '{profile_name}' not found in {CONFIG_PATH}",
            file=sys.stderr,
        )
        print(f"Available profiles: {', '.join(profiles.keys())}", file=sys.stderr)
        sys.exit(1)

    print(f"  Profile: {profile_name}")
    return profiles[profile_name], profile_name, config


def save_config(config):
    """Write config back to disk."""
    with open(CONFIG_PATH, "w") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)
