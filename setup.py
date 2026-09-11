"""Build configuration.

- Regular Python packaging (sdist/wheel, `pip install .`) uses the setuptools
  metadata below; package data is already declared in pyproject.toml.
- On macOS, `python setup.py py2app` builds the standalone "Input from Web.app"
  bundle (used by the GitHub Actions macOS build).
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

setup(
    name="input-from-web",
    version="0.1.0",
    packages=["input_from_web"],
    package_dir={"": "src"},
    package_data={"input_from_web": ["templates/*", "static/*"]},
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
                "CFBundleVersion": "0.1.0",
                "CFBundleShortVersionString": "0.1.0",
                "LSMinimumSystemVersion": "11.0",
                "NSHighResolutionCapable": True,
            },
        }
    },
)