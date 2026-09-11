"""Build configuration.

- Regular Python packaging (sdist/wheel, `pip install .`): metadata is
  declared entirely here; the version is derived from git tags by
  setuptools-scm (see pyproject.toml `[tool.setuptools_scm]`), never hardcoded.
- On macOS, `python setup.py py2app` builds the standalone "Input from Web.app"
  bundle (used by the GitHub Actions macOS build). py2app >= 0.28.9 rejects a
  non-empty `install_requires`, so it is passed as `[]` while building the app
  (runtime deps are pre-installed in the build environment).
"""
import sys
from pathlib import Path

from setuptools import setup

HERE = Path(__file__).parent
PKG_DIR = HERE / "src" / "input_from_web"
SITE = (
    f"lib/python{sys.version_info.major}.{sys.version_info.minor}"
    "/site-packages/input_from_web"
)


def _version() -> str:
    """Resolve the version for the py2app Info.plist."""
    try:
        from setuptools_scm import get_version

        return get_version(root=str(HERE), fallback_version="0.1.0")
    except Exception:
        return "0.1.0"


setup(
    name="input-from-web",
    description="Type on your phone, inject into focused desktop app",
    long_description=(HERE / "README.md").read_text(encoding="utf-8"),
    long_description_content_type="text/markdown",
    use_scm_version={
        "root": ".",
        "fallback_version": "0.1.0",
        "write_to": "src/input_from_web/_version.py",
    },
    packages=["input_from_web"],
    package_dir={"": "src"},
    package_data={"input_from_web": ["templates/*", "static/*"]},
    python_requires=">=3.10",
    install_requires=[] if "py2app" in sys.argv else ["flask", "qrcode"],
    entry_points={"console_scripts": ["input-from-web = input_from_web.cli:main"]},
    app=["macos-launcher.py"],
    data_files=[
        (
            f"{SITE}/templates",
            [str(p.relative_to(HERE)) for p in (PKG_DIR / "templates").glob("*")],
        ),
        (
            f"{SITE}/static",
            [str(p.relative_to(HERE)) for p in (PKG_DIR / "static").glob("*")],
        ),
    ],
    options={
        "py2app": {
            "packages": ["flask", "qrcode", "input_from_web"],
            "iconfile": "icon.icns",
            "plist": {
                "CFBundleName": "Input from Web",
                "CFBundleDisplayName": "Input from Web",
                "CFBundleIdentifier": "io.github.sam-fic.input-from-web",
                "CFBundleVersion": _version(),
                "CFBundleShortVersionString": _version(),
                "LSMinimumSystemVersion": "11.0",
                "NSHighResolutionCapable": True,
            },
        }
    },
)