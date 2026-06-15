"""
WinGhost Monitor — supervision de la performance applicative (CHU Toulouse).

Architecture en 4 couches (cf. diagramme de conception) :

    Couche 1 — Recorder       capture souris/clavier + screenshots horodatés
    Couche 2 — Replayer       rejeu + ancrage visuel OpenCV + DPI/RDP + retry
    Couche 3 — KPI Collector  chronomètre visuel + stockage SQLite + dashboard
    Scheduler                 APScheduler par plage horaire → rapport quotidien

Principe directeur : la mesure de performance repose sur le **chronomètre
visuel** (t_action → écran stable), JAMAIS sur le temps d'injection des
frappes. La latence du clavier sort ainsi de la mesure.
"""

from version import __version__

__all__ = ["__version__"]
