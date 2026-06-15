"""
config.py — Constantes, chemins et plages horaires partagés par les 4 couches.

Aucune valeur « magique » n'est dispersée dans le code : tout réglage de seuil,
de timeout ou de chemin transite par ce module pour rester ajustable d'un seul
endroit (et surchargé par variables d'environnement quand pertinent).
"""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path

# ─── Arborescence des données ────────────────────────────────────────────────
# Surchargée par WINMONITOR_HOME ; par défaut sous le dossier utilisateur.
HOME = Path(os.environ.get("WINMONITOR_HOME", Path.home() / ".winghost-monitor"))

SCENARIOS_DIR = HOME / "scenarios"      # un sous-dossier par scénario (.json + anchors/)
DB_PATH       = HOME / "metrics.db"     # base SQLite des mesures (couche 3)
DASHBOARD_DIR = HOME / "dashboard"      # HTML généré (couche 3)
REPORTS_DIR   = HOME / "reports"        # rapports quotidiens (scheduler)
FALLBACK_DIR  = HOME / "fallback"       # screenshots de diagnostic quand ancrage échoue


def ensure_dirs() -> None:
    """Crée l'arborescence de données si absente (idempotent)."""
    for d in (SCENARIOS_DIR, DASHBOARD_DIR, REPORTS_DIR, FALLBACK_DIR):
        d.mkdir(parents=True, exist_ok=True)


# ─── Plages horaires (couche 3 / scheduler) ──────────────────────────────────
# Chaque plage = (label, heure_début_incluse, heure_fin_exclue) en heure locale.
# Sert à regrouper les mesures « 08h-09h », « 12h », « 17h »… pour la baseline.
TIME_SLOTS: list[tuple[str, int, int]] = [
    ("08h-09h", 8, 9),
    ("09h-12h", 9, 12),
    ("12h-14h", 12, 14),
    ("14h-17h", 14, 17),
    ("17h-19h", 17, 19),
    ("hors-plage", 0, 24),   # filet de sécurité (toujours vrai en dernier)
]


def slot_for(dt: datetime) -> str:
    """Retourne le label de plage horaire correspondant à `dt` (heure locale)."""
    h = dt.hour
    for label, start, end in TIME_SLOTS:
        if label == "hors-plage":
            continue
        if start <= h < end:
            return label
    return "hors-plage"


# ─── Couche 2 — Ancrage visuel (OpenCV matchTemplate) ────────────────────────
ANCHOR_CONFIDENCE     = 0.80     # corrélation minimale pour valider un ancrage
ANCHOR_RETRY_TIMEOUT  = 5.0      # secondes : on retente l'ancrage jusqu'à ce délai
ANCHOR_RETRY_INTERVAL = 0.25     # secondes entre deux tentatives d'ancrage
# Échelles testées (tolérance DPI / compression RDP / AppliDis).
ANCHOR_SCALES = [1.0, 0.95, 1.05, 0.90, 1.10, 0.85, 1.15, 0.80, 1.20]

# ─── Couche 3 — Chronomètre visuel (t_action → écran stable) ─────────────────
STABLE_DIFF_THRESHOLD = 2.0      # diff. moyenne de pixels en-deçà = « pas de changement »
STABLE_FRAMES         = 3        # nb d'images consécutives stables pour déclarer stable
STABLE_POLL_INTERVAL  = 0.05     # secondes entre deux captures pendant le chrono
STABLE_TIMEOUT        = 15.0     # secondes : au-delà, on déclare un timeout (échec)

# ─── Régression vs baseline (couche 3) ───────────────────────────────────────
# Une mesure est « dégradée » si elle dépasse baseline_p95 * ce facteur.
REGRESSION_FACTOR = 1.5
