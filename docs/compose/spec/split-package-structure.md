---
feature: split-package-structure
status: delivered
updated: 2026-02-14
branch: refactor/split-package
commits: 75a91d3..9c11459
---

# Split Package Structure

## Report

**What was built** — The 2144-line monolith was split into a src-layout package `src/input_from_web` with clear module boundaries: CLI bootstrap (`cli.py`), path/platform constants (`paths.py`), config I/O (`config.py`), mutable runtime state (`state.Runtime`), network/QR helpers (`network.py`), autostart management (`autostart.py`), inject orchestration (`inject.py`), platform backends (`backends/windows.py`, `backends/linux.py`), and a Flask app factory (`web.py`). The phone UI shell, CSS, module JS, and pre-paint theme script live under `templates/` and `static/`. Profile config is injected via `#app-config` JSON instead of an inline `__CONFIG__` script assignment. Root `input-from-web.py` is a thin shim; `run.bat`/`run.sh` set `PYTHONPATH=src` and run `python -m input_from_web`. Debian packaging installs the package tree and runs the module via `PYTHONPATH`. A `pyproject.toml` documents metadata and package data.

**Verification** — `python -m input_from_web --help` (PASS); root shim `--help` (PASS); `compileall` on the package (PASS); Flask `test_client` smoke for `/ping`, `/`, `/static/app.css`, `/static/app.js`, `/static/theme-init.js`, `/icon.svg`, `/manifest.json`, `/sw.js`, `/settings` token 403/200 + method flip persist, `/send` empty 400 (PASS); mutual-exclusive autostart flags exit 1 (PASS). Independent review against `75a91d3` found no critical defects (inject timings/chords, token gate, settings persistence, route URLs, CLI permanent-link behavior match).

**Journey log** — Extracting the module script left `const CONFIG = __CONFIG__` inside static JS; fixed by serving a JSON `<script id="app-config">` and `JSON.parse` in `app.js`. `send_from_directory` needs a directory + filename, not a full file path. PowerShell here-strings mangle nested quotes in one-liners; use a temp smoke file instead.

## [S1] Problem

All program logic lives in a single 2144-line `input-from-web.py`: Windows ctypes backend, Linux injection, autostart, config I/O, Flask routes, CLI, and a ~1340-line HTML/CSS/JS template string. This blocks testing, review, and incremental feature work, and mixes platform, web, and frontend concerns in one file.

## [S2] Design

Target layout (src layout, no behavior change):

```
input-from-web.py                 # thin shim → input_from_web.cli:main
pyproject.toml                    # metadata; optional editable install
run.bat / run.sh                  # venv bootstrap + python -m input_from_web
src/input_from_web/
  __init__.py
  __main__.py
  cli.py                          # argparse, bootstrap, QR + app.run
  paths.py                        # IS_WIN, package/root paths, config/autostart paths
  config.py                       # DEFAULT_CONFIG, load_or_create_config, save_config
  state.py                        # Runtime dataclass (replaces module globals)
  network.py                      # get_lan_ip, print_startup_qr
  autostart.py                    # install/uninstall/installed + templates
  inject.py                       # inject_text orchestration
  backends/
    __init__.py
    windows.py                    # SendInput / clipboard
    linux.py                      # ydotool / wl-copy
  web.py                          # Flask app factory + routes + ping filter
  templates/index.html            # page shell (__CONFIG__ etc.)
  static/app.css
  static/app.js                   # type=module page logic
  static/theme-init.js            # head pre-paint theme script
  static/icon.svg
```

Contracts:

- `create_app(runtime: Runtime) -> Flask` builds the app; routes read runtime from `app.config["RUNTIME"]` (no import-time mutable globals).
- `Runtime` holds: token, use_token, method, auto_paste, paste_key, auto_press_enter, profile, full_config, current_profile_name.
- `inject_text(runtime, text)` uses the same platform algorithm as today.
- Root `input-from-web.py` remains a thin compatibility shim adding `src/` to `sys.path` then calling `main()`.
- `run.bat` / `run.sh` invoke `python -m input_from_web` with `PYTHONPATH=src`.
- Debian: `rules` installs `src/input_from_web` under `/usr/share/input-from-web/input_from_web`; wrapper sets `PYTHONPATH` and runs `-m input_from_web`.
- Static assets served at `/static/*`; `/`, `/ping`, `/send`, `/settings`, `/autostart`, `/manifest.json`, `/icon.svg`, `/sw.js` keep current URLs.
- Template placeholders `__CONFIG__`, `__LANG__`, `__TITLE__`, `__LABEL_TYPE_HERE__` preserved (string replace; no Jinja `{{` in assets). Profile JSON is also mirrored into `#app-config` for the extracted `app.js`.

Out of scope for behavior: no new features, no dependency upgrades, no HTTPS, no test framework mandate (smoke checks only unless cheap).

## [S3] Out of Scope

- Functional/UI changes to the phone page or inject timing
- Packaging to PyPI / pip install in production
- Rewriting debian to dh-python/setup.py
- Extracting further frontend frameworks or bundlers

## Tasks

- [x] T1: Scaffold package modules with moved logic — acceptance: `python -m input_from_web --help` works from worktree with PYTHONPATH=src (covers: S2)
- [x] T2: Extract HTML/CSS/JS to templates/static and wire Flask factory — acceptance: GET / returns page with substituted CONFIG; GET /static/app.js and app.css return 200 (covers: S2)
- [x] T3: Thin shim + update run.bat/run.sh/debian/rules/wrapper/README paths — acceptance: documented commands still start the app entry (covers: S2)
- [x] T4: Smoke verify ping/send/settings/autostart routes and CLI flags — acceptance: scripted smoke of routes and `--help`/`--install-autostart` dry paths (covers: S2)
