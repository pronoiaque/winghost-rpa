"""Couche 2 — Replayer : ancrage visuel + DPI/RDP + injection + gestion d'erreur."""

from winmonitor.replayer.anchor import AnchorMatch, locate_template
from winmonitor.replayer.replayer import ActionOutcome, Replayer, RunResult

__all__ = [
    "AnchorMatch",
    "locate_template",
    "Replayer",
    "RunResult",
    "ActionOutcome",
]
