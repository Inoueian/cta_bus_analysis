"""Acceptance tests for specs/package-migration.md: the `cta/` package is the only import surface."""

from __future__ import annotations

import importlib
import json
import pkgutil
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
NOTEBOOKS = REPO_ROOT / "notebooks"
LEGACY_MODULES = ("cta_api", "dlsd_run_quality", "michigan_ave_segment")

_SYS_PATH_INSERT = re.compile(r"sys\.path\.insert\((.*?)\)", re.DOTALL)
_BARE_IMPORT = re.compile(r"^\s*(?:from|import)\s+(" + "|".join(LEGACY_MODULES) + r")\b", re.MULTILINE)


def _code_cells(nb_path: Path) -> list[str]:
    nb = json.loads(nb_path.read_text())
    return ["".join(c["source"]) for c in nb["cells"] if c["cell_type"] == "code"]


def test_every_cta_module_imports():
    import cta

    names = sorted(m.name for m in pkgutil.iter_modules(cta.__path__))
    assert set(LEGACY_MODULES) <= set(names), names
    for name in names:
        importlib.import_module(f"cta.{name}")


def test_no_importable_code_under_notebooks():
    assert sorted(NOTEBOOKS.glob("*.py")) == []


def test_notebooks_do_not_put_notebooks_dir_on_sys_path():
    notebooks = sorted(NOTEBOOKS.glob("*.ipynb"))
    assert notebooks, "no notebooks found"
    offenders = []
    for nb_path in notebooks:
        for src in _code_cells(nb_path):
            for m in _SYS_PATH_INSERT.finditer(src):
                if "notebooks" in m.group(1):
                    offenders.append((nb_path.name, m.group(0)))
            for m in _BARE_IMPORT.finditer(src):
                offenders.append((nb_path.name, m.group(0).strip()))
    assert offenders == []


def test_repo_root_resolves_to_repo_root():
    from cta.michigan_ave_segment import repo_root

    assert repo_root() == REPO_ROOT
    assert (repo_root() / "CLAUDE.md").is_file()
