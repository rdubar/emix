"""Support ``python -m emix``."""

from __future__ import annotations

import sys

from emix.cli import main

if __name__ == "__main__":
    sys.exit(main())
