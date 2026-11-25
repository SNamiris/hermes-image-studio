#!/usr/bin/env python3
"""Run the prompt kit from the installed plugin."""

from pathlib import Path
import sys


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
    from prompt_kit.cli import main

    raise SystemExit(main())
