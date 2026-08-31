"""Allow running the CLI as ``python -m resilio_backup_store``."""

from __future__ import annotations

import sys

from .cli import main

if __name__ == "__main__":
    sys.exit(main())
