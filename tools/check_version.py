"""
check_version.py — Garde-fou CI : version.py DOIT être identique à pyproject.toml.

Évite tout problème de guillemets shell (PowerShell/bash) en faisant la
comparaison entièrement en Python. Sortie 0 si cohérent, 1 sinon.
Lancé par .github/workflows/build-windows.yml avant le build.
"""

import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from version import __version__ as app_version  # noqa: E402

with open(ROOT / "pyproject.toml", "rb") as f:
    proj_version = tomllib.load(f)["project"]["version"]

print(f"version.py = {app_version} ; pyproject.toml = {proj_version}")

if app_version != proj_version:
    print("ERREUR : incohérence de version entre version.py et pyproject.toml.",
          file=sys.stderr)
    sys.exit(1)

print("Versions cohérentes.")
