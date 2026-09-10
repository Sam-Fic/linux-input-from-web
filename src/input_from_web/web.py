"""Flask application factory and HTTP routes."""

import json
import logging
import os
import subprocess
import sys

from flask import Flask, Response, abort, request, send_from_directory

from .autostart import (
    autostart_installed,
    install_autostart,
    uninstall_autostart,
)
from .config import save_config
from .inject import inject_text
from .paths import STATIC_DIR, TEMPLATES_DIR
from .state import Runtime


class _PingFilter(logging.Filter):
    def filter(self, record):
        return "/ping" not in record.getMessage()


def create_app(runtime: Runtime) -> Flask:
    app = Flask(
        __name__,
        template_folder=TEMPLATES_DIR,
        static_folder=STATIC_DIR,
        static_url_path="/static",
    )
    app.config["RUNTIME"] = runtime

    werkzeug_log = logging.getLogger("werkzeug")
    werkzeug_log.addFilter(_PingFilter())

    def check_token(rt: Runtime) -> None:
        if rt.use_token and request.args.get("token") != rt.token:
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
        return send_from_directory(STATIC_DIR, "icon.svg", mimetype="image/svg+xml")

    @app.route("/sw.js")
    def service_worker():
        return Response(
            'self.addEventListener("fetch", e => e.respondWith(fetch(e.request)));',
            mimetype="application/javascript",
        )

    @app.route("/")
    def index():
        rt = app.config["RUNTIME"]
        profile_json = json.dumps(rt.profile, ensure_ascii=False)

        lang_override = request.args.get("lang", "").lower()
        if lang_override in ("zh", "en"):
            ui_lang = lang_override
        else:
            accept = request.headers.get("Accept-Language", "")
            ui_lang = "zh" if accept.lower().startswith("zh") else "en"
        ui_title = "输入" if ui_lang == "zh" else "Input"
        ui_label = "在此输入…" if ui_lang == "zh" else "Type here..."

        with open(os.path.join(TEMPLATES_DIR, "index.html"), encoding="utf-8") as f:
            html = f.read()
        html = (
            html.replace("__CONFIG__", profile_json)
            .replace("__LANG__", ui_lang)
            .replace("__TITLE__", ui_title)
            .replace("__LABEL_TYPE_HERE__", ui_label)
        )
        return html

    @app.route("/send", methods=["POST"])
    def send():
        rt = app.config["RUNTIME"]
        check_token(rt)
        data = request.get_json(force=True)
        text = data.get("text", "")
        if not text:
            return {"error": "empty"}, 400
        try:
            inject_text(rt, text)
        except (
            subprocess.CalledProcessError,
            OSError,
            subprocess.TimeoutExpired,
        ) as e:
            print(f"Injection failed: {e}", file=sys.stderr)
            return {"error": "injection failed"}, 500
        return {"ok": True}

    @app.route("/autostart", methods=["GET", "POST"])
    def autostart():
        rt = app.config["RUNTIME"]
        check_token(rt)
        if request.method == "GET":
            return {"installed": autostart_installed()}
        action = (request.get_json(force=True, silent=True) or {}).get("action")
        if action == "install":
            ok, msg = install_autostart()
            return {"ok": ok, "message": msg}
        if action == "uninstall":
            ok, msg = uninstall_autostart()
            return {"ok": ok, "message": msg}
        return {"error": "unknown action"}, 400

    @app.route("/settings", methods=["GET", "POST"])
    def settings():
        """Read or update profile-level toggles. Token-protected, like /send."""
        rt = app.config["RUNTIME"]
        check_token(rt)
        if request.method == "GET":
            return {
                "method": rt.method,
                "auto_paste": rt.auto_paste,
                "paste_key": rt.paste_key,
                "auto_press_enter": rt.auto_press_enter,
                "use_security_token": rt.use_token,
                "voice_send_enabled": (rt.profile.get("voice_send") or {}).get(
                    "enabled", True
                ),
            }
        data = request.get_json(force=True, silent=True) or {}
        dirty = False
        if "method" in data and data["method"] in ("type", "clipboard"):
            rt.method = data["method"]
            rt.profile["method"] = rt.method
            dirty = True
        if "auto_paste" in data:
            rt.auto_paste = bool(data["auto_paste"])
            rt.profile["auto_paste"] = rt.auto_paste
            dirty = True
        if "paste_key" in data:
            requested = str(data["paste_key"]).strip().lower()
            if requested in ("ctrl+v", "ctrl+shift+v"):
                rt.paste_key = requested
                rt.profile["paste_key"] = rt.paste_key
                dirty = True
            else:
                return {"error": "paste_key must be 'ctrl+v' or 'ctrl+shift+v'"}, 400
        if "auto_press_enter" in data:
            rt.auto_press_enter = bool(data["auto_press_enter"])
            rt.profile["auto_press_enter"] = rt.auto_press_enter
            dirty = True
        if "use_security_token" in data:
            rt.use_token = bool(data["use_security_token"])
            rt.profile["use_security_token"] = rt.use_token
            dirty = True
        if "voice_send_enabled" in data:
            vs = rt.profile.setdefault("voice_send", {})
            vs["enabled"] = bool(data["voice_send_enabled"])
            dirty = True
        if dirty:
            try:
                rt.persist_profile(save_config)
            except OSError as e:
                print(f"Failed to persist settings: {e}", file=sys.stderr)
        return {
            "ok": True,
            "method": rt.method,
            "auto_paste": rt.auto_paste,
            "paste_key": rt.paste_key,
            "auto_press_enter": rt.auto_press_enter,
            "use_security_token": rt.use_token,
            "voice_send_enabled": (rt.profile.get("voice_send") or {}).get(
                "enabled", True
            ),
        }

    return app
