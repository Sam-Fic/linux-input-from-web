"""Command-line entry: bootstrap config, token, QR code, and Flask server."""

import argparse
import os
import secrets
import sys

from .autostart import install_autostart, uninstall_autostart
from .config import load_or_create_config, save_config
from .network import get_lan_ip, print_startup_qr
from .paths import TEMPLATES_DIR
from .state import Runtime
from .web import create_app


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Type on your phone, paste on your desktop."
    )
    parser.add_argument(
        "--method",
        choices=["clipboard", "type"],
        default=None,
        help="Override profile method. type: simulate keystrokes "
        "(ydotool on Linux, SendInput on Windows, AppleScript on macOS). "
        "clipboard: copy only (wl-copy / Windows clipboard).",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=None,
        help="Override profile port (default: 5123)",
    )
    parser.add_argument(
        "--profile",
        default=None,
        help="Config profile name (default: from config file)",
    )
    parser.add_argument(
        "--permanent-link",
        action="store_true",
        help="Reuse a stored token across sessions. "
        "QR shows a clean URL; phone remembers the token.",
    )
    parser.add_argument(
        "--permanent-link-refresh",
        action="store_true",
        help="Replace the stored permanent token with a new one. "
        "Implies --permanent-link.",
    )
    parser.add_argument(
        "--install-autostart",
        action="store_true",
        help="Install a user autostart entry (opens a terminal with the "
        "QR code on login). Detects the available terminal emulator.",
    )
    parser.add_argument(
        "--uninstall-autostart",
        action="store_true",
        help="Remove the user autostart entry if present.",
    )
    args = parser.parse_args(argv)

    if args.install_autostart or args.uninstall_autostart:
        if args.install_autostart and args.uninstall_autostart:
            print(
                "Error: --install-autostart and --uninstall-autostart are mutually exclusive.",
                file=sys.stderr,
            )
            return 1
        if args.install_autostart:
            ok, msg = install_autostart()
        else:
            ok, msg = uninstall_autostart()
        print(msg)
        return 0 if ok else 1

    profile, profile_name, full_config = load_or_create_config(args.profile)
    runtime = Runtime(
        token=secrets.token_urlsafe(32),
        use_token=profile.get("use_security_token", True),
        permanent_link=args.permanent_link or args.permanent_link_refresh,
        method=args.method or profile.get("method", "type"),
        auto_paste=profile.get("auto_paste", False),
        paste_key=profile.get("paste_key", "ctrl+v"),
        auto_press_enter=profile.get("auto_press_enter", False),
        profile=profile,
        full_config=full_config,
        current_profile_name=profile_name,
    )

    permanent_is_new = False
    if runtime.permanent_link and runtime.use_token:
        stored = profile.get("permanent_token")
        if args.permanent_link_refresh and stored:
            print("  Replacing permanent token with a new one.")
            stored = None
        if stored:
            runtime.token = stored
            print("  Using permanent token from config.")
        else:
            permanent_is_new = True
            profile["permanent_token"] = runtime.token
            full_config["profiles"][profile_name] = profile
            save_config(full_config)
            print("  Generated and saved permanent token to config.")

    if not runtime.use_token:
        print("\n\033[1;97;41m  WARNING: security token is DISABLED  \033[0m")
        print(
            "\033[1;31m  Anyone on your network can send keystrokes to this machine!\033[0m"
        )
        print("\033[1;31m  Only run this way on a trusted private network.\033[0m\n")

    host = get_lan_ip()
    port = args.port or profile.get("port", 5123)

    base_url = f"http://{host}:{port}/"
    token_url = f"{base_url}?token={runtime.token}" if runtime.use_token else base_url

    if runtime.permanent_link and runtime.use_token:
        if permanent_is_new:
            qr_url = token_url
            print(f"\n  First-time setup (scan QR): {token_url}")
            print(f"  Bookmark URL (next time):   {base_url}\n")
        else:
            qr_url = base_url
            print(f"\n  QR URL (bookmark): {base_url}")
            print(f"  Setup URL:         {token_url}\n")
    else:
        qr_url = token_url
        print(f"\n  URL: {token_url}\n")

    print_startup_qr(qr_url)

    # Fail loudly if package data was not installed/copied.
    if not os.path.isdir(TEMPLATES_DIR):
        print(f"Error: templates directory missing: {TEMPLATES_DIR}", file=sys.stderr)
        return 1

    app = create_app(runtime)
    app.run(host=host, port=port, debug=False)
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
