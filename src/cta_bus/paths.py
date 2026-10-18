"""Repository paths for local caches, reference snapshots, and plot style.

Assumes an editable install (``pip install -e .``) so paths resolve inside the repo.
"""

from __future__ import annotations

from pathlib import Path


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


DATA_DIR = repo_root() / "data"
MANSUETO_CACHE_DIR = DATA_DIR / "mansueto"
API_CACHE_DIR = DATA_DIR / "cta_api_cache"
REFERENCE_DIR = repo_root() / "reference"
PLOT_STYLE = Path(__file__).resolve().parent / "cta_analysis.mplstyle"
