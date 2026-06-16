"""
paths.py — Résolution des chemins compatible exécution « gelée » (PyInstaller).

Deux notions distinctes :

  • resource_path(rel) : ressource EN LECTURE SEULE embarquée dans le binaire
    (ex. assets/logo_chu.png). Sous PyInstaller, les fichiers ajoutés via
    --add-data sont extraits dans sys._MEIPASS.

  • data_dir() : répertoire INSCRIPTIBLE pour les données d'exécution
    (scénarios, rapports, journaux, base SQLite). Ne JAMAIS écrire dans le
    bundle (dossier temporaire en lecture seule sous one-file).

Comportement :
  - En développement (non gelé) : on conserve le comportement historique
    (chemins relatifs au répertoire de travail courant), pour ne rien casser.
  - En binaire gelé : ressources depuis _MEIPASS ; données à côté de l'exe si
    le dossier est inscriptible, sinon %APPDATA%\\WinGhost (repli propre).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

APP_NAME = "WinGhost"


def is_frozen() -> bool:
    """Vrai si l'on tourne dans un binaire PyInstaller / gelé."""
    return bool(getattr(sys, "frozen", False))


def resource_path(rel: str | Path) -> Path:
    """Chemin absolu d'une ressource en lecture seule incluse dans le bundle."""
    if is_frozen():
        base = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    else:
        base = Path(__file__).resolve().parent
    return base / rel


def _writable(directory: Path) -> bool:
    """Teste si `directory` est inscriptible (création d'un fichier témoin)."""
    try:
        directory.mkdir(parents=True, exist_ok=True)
        probe = directory / ".winghost_write_test"
        probe.touch()
        probe.unlink()
        return True
    except OSError:
        return False


def data_dir() -> Path:
    """
    Répertoire inscriptible pour les données d'exécution.
    - dev  : répertoire de travail courant (comportement historique)
    - gelé : dossier de l'exe si inscriptible, sinon %APPDATA%\\WinGhost
    """
    if is_frozen():
        exe_dir = Path(sys.executable).resolve().parent
        if _writable(exe_dir):
            return exe_dir
        appdata = Path(os.environ.get("APPDATA") or Path.home()) / APP_NAME
        appdata.mkdir(parents=True, exist_ok=True)
        return appdata
    return Path.cwd()


def data_path(rel: str | Path) -> Path:
    """Raccourci : sous-chemin inscriptible (le parent est créé si besoin)."""
    p = data_dir() / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    return p
