"""
official_log.py — Journal officiel d'exécution pour WinGhost RPA v4.

Enregistre chaque exécution de scénario dans un fichier CSV mensuel (séparateur
point-virgule, encodage UTF-8 BOM pour compatibilité Excel).

Format des colonnes :
    app_name;scenario_name;execution_date;duration_s;status;ok_count;total_count;run_id

Valeurs du champ status :
    SUCCÈS  — toutes les actions sont OK (aucun skip, aucune erreur)
    PARTIEL — au moins un skip, mais aucune erreur
    ÉCHEC   — au moins une erreur

Fichiers produits :
    logs/official_YYYYMM.csv  (un fichier par mois)

API publique :
    init_logs()
        Crée le répertoire logs/ si nécessaire.

    append_entry(app_name, scenario_name, execution_date, duration_s,
                 status, ok_count, total_count, run_id)
        Ajoute une ligne au fichier du mois courant (crée l'en-tête si besoin).

    get_recent_entries(max_lines=200) -> list[dict]
        Lit les deux fichiers mensuels les plus récents et retourne les
        max_lines dernières entrées triées du plus ancien au plus récent.

    get_all_log_paths() -> list[Path]
        Retourne la liste de tous les fichiers CSV de log existants,
        triés par ordre chronologique.
"""

import csv
import datetime
import io
from pathlib import Path

# ─── Configuration ────────────────────────────────────────────────────────────

LOGS_DIR = Path("logs")
LOGS_DIR.mkdir(exist_ok=True)

_CSV_SEP     = ";"
_ENCODING    = "utf-8-sig"   # UTF-8 BOM — Excel l'ouvre correctement sans conversion
_FIELDNAMES  = [
    "app_name",
    "scenario_name",
    "execution_date",
    "duration_s",
    "status",
    "ok_count",
    "total_count",
    "run_id",
]

# Valeurs autorisées pour le champ status
STATUS_SUCCESS = "SUCCÈS"
STATUS_PARTIAL = "PARTIEL"
STATUS_FAILURE = "ÉCHEC"


# ─── API publique ─────────────────────────────────────────────────────────────

def init_logs() -> None:
    """Crée le répertoire LOGS_DIR s'il n'existe pas encore."""
    LOGS_DIR.mkdir(exist_ok=True)


def append_entry(
    app_name: str,
    scenario_name: str,
    execution_date: str,
    duration_s: float,
    status: str,
    ok_count: int,
    total_count: int,
    run_id: int,
) -> Path:
    """
    Ajoute une entrée dans le fichier CSV du mois en cours.

    Parameters
    ----------
    app_name        : nom de l'application (ex. « Notepad »)
    scenario_name   : nom du scénario rejoué
    execution_date  : date/heure ISO ou chaîne lisible (ex. « 2026-06-12T14:30:00 »)
    duration_s      : durée totale du run en secondes (float)
    status          : STATUS_SUCCESS | STATUS_PARTIAL | STATUS_FAILURE
    ok_count        : nombre d'actions avec statut « ok »
    total_count     : nombre total d'actions traitées
    run_id          : identifiant du run SQLite

    Returns
    -------
    Path du fichier CSV dans lequel la ligne a été écrite.
    """
    init_logs()
    month_tag = datetime.datetime.now().strftime("%Y%m")
    csv_path  = LOGS_DIR / f"official_{month_tag}.csv"

    write_header = not csv_path.exists() or csv_path.stat().st_size == 0

    with open(csv_path, "a", encoding=_ENCODING, newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=_FIELDNAMES, delimiter=_CSV_SEP)
        if write_header:
            writer.writeheader()
        writer.writerow({
            "app_name":       app_name,
            "scenario_name":  scenario_name,
            "execution_date": execution_date,
            "duration_s":     round(float(duration_s), 3),
            "status":         status,
            "ok_count":       int(ok_count),
            "total_count":    int(total_count),
            "run_id":         int(run_id),
        })

    return csv_path


def get_recent_entries(max_lines: int = 200) -> list[dict]:
    """
    Lit les deux fichiers mensuels les plus récents et retourne les
    *max_lines* dernières entrées, triées du plus ancien au plus récent.

    Parameters
    ----------
    max_lines : nombre maximum d'entrées retournées (défaut 200)

    Returns
    -------
    list[dict] avec les clés correspondant aux colonnes du CSV.
    """
    paths = get_all_log_paths()
    # Deux fichiers les plus récents
    recent_paths = paths[-2:] if len(paths) >= 2 else paths

    entries: list[dict] = []
    for p in recent_paths:
        try:
            with open(p, encoding=_ENCODING, newline="") as fh:
                reader = csv.DictReader(fh, delimiter=_CSV_SEP)
                for row in reader:
                    entries.append(dict(row))
        except Exception:
            pass

    # Retourner les max_lines dernières entrées (déjà dans l'ordre d'écriture)
    return entries[-max_lines:]


def get_all_log_paths() -> list[Path]:
    """
    Retourne tous les fichiers official_YYYYMM.csv présents dans LOGS_DIR,
    triés par ordre chronologique (du plus ancien au plus récent).
    """
    init_logs()
    files = sorted(LOGS_DIR.glob("official_*.csv"))
    return files
