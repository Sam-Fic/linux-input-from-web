#!/usr/bin/env python3
"""Compatibility entry point. Prefer: python -m input_from_web"""
import os
import sys

_ROOT = os.path.dirname(os.path.abspath(__file__))
_SRC = os.path.join(_ROOT, "src")
if os.path.isdir(_SRC) and _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from input_from_web.cli import main

if __name__ == "__main__":
    sys.exit(main() or 0)
