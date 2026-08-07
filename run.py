"""Launcher kept at the project root so `python run.py` works and PyInstaller
has an entry script whose directory does not shadow stdlib modules."""

import sys

from app.main import main

if __name__ == "__main__":
    sys.exit(main())
