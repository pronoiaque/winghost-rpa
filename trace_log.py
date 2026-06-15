"""
trace_log.py — Traçage multi-contextuel (enregistrement ↔ rejeu) — v6.4.2.

Écrit un journal horodaté à la milliseconde dans
    <data_dir>/debug/winghost_trace.log
couvrant les DEUX phases :

  • ENREGISTREMENT : chaque touche capturée, chaque vidage de tampon, chaque
    action « type »/« key » créée (avec le texte exact).
  • REJEU : pour chaque action clavier, la fenêtre au premier plan AVANT le clic,
    APRÈS le clic (le focus a-t-il bougé ?), le contrôle qui a le focus, et le
    code de retour de SendInput caractère par caractère.

But : prouver où partent réellement les frappes au moment du rejeu — le seul
moyen de distinguer « frappe non émise » de « frappe émise vers la mauvaise
fenêtre » (focus resté sur WinGhost / appli cible jamais activée).
"""

from __future__ import annotations

import logging
from pathlib import Path

_log = logging.getLogger("winghost.trace")
_configured = False


def setup() -> Path | None:
    """Active le fichier de trace (idempotent). Renvoie le chemin du journal."""
    global _configured
    try:
        from paths import data_dir
        d = data_dir() / "debug"
        d.mkdir(parents=True, exist_ok=True)
        path = d / "winghost_trace.log"
        if not _configured:
            fh = logging.FileHandler(path, encoding="utf-8")
            fh.setLevel(logging.DEBUG)
            fh.setFormatter(logging.Formatter(
                "%(asctime)s [%(name)s] %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S"))
            _log.addHandler(fh)
            _log.setLevel(logging.DEBUG)
            _log.propagate = False
            _configured = True
            _log.info("──────── Nouvelle session de trace ────────")
        return path
    except Exception:
        return None


def log(msg: str, *args) -> None:
    """Écrit une ligne de trace (no-op si le fichier n'a pu être ouvert)."""
    try:
        if not _configured:
            setup()
        _log.info(msg, *args)
    except Exception:
        pass


def trace_path() -> Path | None:
    try:
        from paths import data_dir
        return data_dir() / "debug" / "winghost_trace.log"
    except Exception:
        return None
