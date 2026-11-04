"""Pytest configuration: ensure repo root is on sys.path so `cta` and `scripts` import without installing."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
