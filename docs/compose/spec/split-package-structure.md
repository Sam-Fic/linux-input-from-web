---
feature: split-package-structure
status: designed
updated: 2026-02-14
branch: refactor/split-package
commits: 75a91d3..HEAD
---

# Split Package Structure

## Report

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
  templates/index.html            # Jinja-ready page shell (__CONFIG__ etc.)
  static/app.css
  static/app.js                   # type=module page logic
  static/theme-init.js            # head pre-paint theme script
  static/icon.svg
```

Contracts:

- `create_app(runtime: Runtime) -> Flask` builds the app; routes read runtime from `app.config["RUNTIME"]` (no import-time mutable globals).
- `Runtime` holds: token, use_token, method, auto_paste, paste_key, auto_press_enter, profile, full_config, current_profile_name.
- `inject_text(runtime, text)` uses the same platform algorithm as today.
- Root `input-from-web.py` remains a ~10-line compatibility shim adding `src/` to `sys.path` then calling `main()`.
- `run.bat` / `run.sh` invoke `python -m input_from_web` with `PYTHONPATH=src`.
- Debian: `rules` installs `src/input_from_web` under `/usr/share/input-from-web/input_from_web`; wrapper sets `PYTHONPATH` and runs `-m input_from_web`.
- Static assets served at `/static/*`; `/`, `/ping`, `/send`, `/settings`, `/autostart`, `/manifest.json`, `/icon.svg`, `/sw.js` keep current URLs.
- Template placeholders `__CONFIG__`, `__LANG__`, `__TITLE__`, `__LABEL_TYPE_HERE__` preserved (string replace; no Jinja `{{` in assets).

Out of scope for behavior: no new features, no dependency upgrades, no HTTPS, no test framework mandate (smoke checks only unless cheap).

## [S3] Out of Scope

- Functional/UI changes to the phone page or inject timing
- Packaging to PyPI / pip install in production
- Rewriting debian to dh-python/setup.py
- Extracting further frontend frameworks or bundlers

## Tasks

- [ ] T1: Scaffold package modules with moved logic — acceptance: `python -m input_from_web --help` works from worktree with PYTHONPATH=src (covers: S2)
- [ ] T2: Extract HTML/CSS/JS to templates/static and wire Flask factory — acceptance: GET / returns page with substituted CONFIG; GET /static/app.js and app.css return 200 (covers: S2)
- [ ] T3: Thin shim + update run.bat/run.sh/debian/rules/wrapper/README paths — acceptance: documented commands still start the app entry (covers: S2)
- [ ] T4: Smoke verify ping/send/settings/autostart routes and CLI flags — acceptance: scripted smoke of routes and `--help`/`--install-autostart` dry paths (covers: S2)
