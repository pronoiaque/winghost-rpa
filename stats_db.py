"""
stats_db.py — Stockage SQLite multi-runs pour WinGhost RPA v4.

Schéma :
  sessions       → une entrée par fichier session JSON (+ scenario_name)
  runs           → N runs par session (run_number, started_at, stats résumées, total_duration_s)
  action_results → résultats détaillés par action (label, timing ms, screenshot_b64, app_name)

API publique :
  init_db()             — crée les tables si elles n'existent pas + migration colonnes manquantes
  upsert_session(...)   → session_id
  insert_run(...)       → run_id
  finish_run(...)       — clôture un run avec les stats agrégées
  insert_action_result(...)
  get_all_sessions()    → list[dict]
  get_session_runs(session_id) → list[dict]
  get_run_actions(run_id)      → list[dict]
  get_label_stats(session_id)  → list[dict]  (avg/max/min ms + success rate + app_name par label)
  get_hourly_stats(session_id) → list[dict]  (avg ms par heure de la journée)
  export_csv(session_id)       → str  (CSV complet, inclut app_name et scenario_name)
"""

import csv
import datetime
import io
import sqlite3
from pathlib import Path
from typing import Optional

DB_PATH = Path("winghost_stats.db")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    name          TEXT    NOT NULL,
    filepath      TEXT    NOT NULL UNIQUE,
    action_count  INTEGER DEFAULT 0,
    created_at    TEXT    NOT NULL,
    scenario_name TEXT    DEFAULT ''
);

CREATE TABLE IF NOT EXISTS runs (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id       INTEGER NOT NULL REFERENCES sessions(id),
    run_number       INTEGER NOT NULL,
    started_at       TEXT    NOT NULL,
    ended_at         TEXT,
    total            INTEGER DEFAULT 0,
    ok_count         INTEGER DEFAULT 0,
    skip_count       INTEGER DEFAULT 0,
    error_count      INTEGER DEFAULT 0,
    avg_response_ms  REAL,
    max_response_ms  REAL,
    total_duration_s REAL,           -- temps de bout en bout (horloge murale)
    app_response_ms  REAL            -- temps applicatif cumulé (somme des réponses)
);

CREATE TABLE IF NOT EXISTS action_results (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id           INTEGER NOT NULL REFERENCES runs(id),
    action_index     INTEGER NOT NULL,
    action_type      TEXT,
    label            TEXT,
    x                INTEGER,
    y                INTEGER,
    ocr_score        REAL,
    visual_ok        INTEGER,        -- 1=ok / 0=ko / NULL=non vérifié
    response_time_ms REAL,
    status           TEXT,           -- 'ok' | 'skip' | 'error'
    error_msg        TEXT,
    screenshot_b64   TEXT,           -- PNG base64 (nullable, peut être volumineux)
    replayed_at      TEXT NOT NULL,  -- ISO datetime pour l'analyse heure-par-heure
    app_name         TEXT DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_results_run    ON action_results(run_id);
CREATE INDEX IF NOT EXISTS idx_runs_session   ON runs(session_id);
CREATE INDEX IF NOT EXISTS idx_results_label  ON action_results(label);
CREATE INDEX IF NOT EXISTS idx_results_status ON action_results(status);
"""


# ─── Migration ────────────────────────────────────────────────────────────────

def _migrate(conn: sqlite3.Connection) -> None:
    """
    Ajoute les colonnes manquantes dans les DBs existantes créées avant v4.
    Idempotent : ne fait rien si la colonne est déjà présente.
    """
    for table, col, typedef in [
        ("sessions",       "scenario_name",   "TEXT DEFAULT ''"),
        ("runs",           "total_duration_s", "REAL"),
        ("runs",           "app_response_ms",  "REAL"),
        ("action_results", "app_name",         "TEXT DEFAULT ''"),
    ]:
        existing = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
        if col not in existing:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {typedef}")


# ─── Connexion ────────────────────────────────────────────────────────────────

def _conn(db_path: Path = DB_PATH) -> sqlite3.Connection:
    c = sqlite3.connect(str(db_path))
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys = ON")
    c.execute("PRAGMA journal_mode = WAL")
    return c


def init_db(db_path: Path = DB_PATH) -> None:
    with _conn(db_path) as c:
        c.executescript(_SCHEMA)
        _migrate(c)


# ─── Écriture ─────────────────────────────────────────────────────────────────

def upsert_session(filepath: str, name: str, action_count: int,
                   scenario_name: str = "",
                   db_path: Path = DB_PATH) -> int:
    with _conn(db_path) as c:
        row = c.execute(
            "SELECT id FROM sessions WHERE filepath = ?", (filepath,)
        ).fetchone()
        if row:
            c.execute(
                "UPDATE sessions SET action_count = ?, name = ?, scenario_name = ? WHERE id = ?",
                (action_count, name, scenario_name, row["id"]),
            )
            return int(row["id"])
        cur = c.execute(
            "INSERT INTO sessions (name, filepath, action_count, created_at, scenario_name) "
            "VALUES (?,?,?,?,?)",
            (name, filepath, action_count,
             datetime.datetime.now().isoformat(timespec="seconds"),
             scenario_name),
        )
        return int(cur.lastrowid)


def next_run_number(session_id: int, db_path: Path = DB_PATH) -> int:
    with _conn(db_path) as c:
        row = c.execute(
            "SELECT COALESCE(MAX(run_number), 0) + 1 AS n FROM runs WHERE session_id = ?",
            (session_id,),
        ).fetchone()
        return int(row["n"])


def insert_run(session_id: int, run_number: int, started_at: str,
               db_path: Path = DB_PATH) -> int:
    with _conn(db_path) as c:
        cur = c.execute(
            "INSERT INTO runs (session_id, run_number, started_at) VALUES (?,?,?)",
            (session_id, run_number, started_at),
        )
        return int(cur.lastrowid)


def finish_run(run_id: int, ended_at: str,
               total: int, ok: int, skip: int, errors: int,
               avg_ms: Optional[float], max_ms: Optional[float],
               total_duration_s: Optional[float] = None,
               app_response_ms: Optional[float] = None,
               db_path: Path = DB_PATH) -> None:
    with _conn(db_path) as c:
        c.execute(
            """UPDATE runs
               SET ended_at=?, total=?, ok_count=?, skip_count=?,
                   error_count=?, avg_response_ms=?, max_response_ms=?,
                   total_duration_s=?, app_response_ms=?
               WHERE id=?""",
            (ended_at, total, ok, skip, errors, avg_ms, max_ms,
             total_duration_s, app_response_ms, run_id),
        )


def insert_action_result(
    run_id: int,
    action_index: int,
    action_type: str,
    label: str,
    x: Optional[int],
    y: Optional[int],
    ocr_score: Optional[float],
    visual_ok: Optional[bool],
    response_time_ms: Optional[float],
    status: str,
    error_msg: Optional[str],
    screenshot_b64: Optional[str],
    replayed_at: str,
    app_name: str = "",
    db_path: Path = DB_PATH,
) -> None:
    visual_int = None if visual_ok is None else (1 if visual_ok else 0)
    with _conn(db_path) as c:
        c.execute(
            """INSERT INTO action_results
               (run_id, action_index, action_type, label, x, y, ocr_score,
                visual_ok, response_time_ms, status, error_msg,
                screenshot_b64, replayed_at, app_name)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (run_id, action_index, action_type, label, x, y, ocr_score,
             visual_int, response_time_ms, status, error_msg,
             screenshot_b64, replayed_at, app_name),
        )


# ─── Lecture ──────────────────────────────────────────────────────────────────

def get_all_sessions(db_path: Path = DB_PATH) -> list[dict]:
    with _conn(db_path) as c:
        rows = c.execute(
            """SELECT s.*,
                      COUNT(r.id)            AS run_count,
                      AVG(r.avg_response_ms) AS global_avg_ms,
                      MAX(r.started_at)      AS last_run_at
               FROM sessions s
               LEFT JOIN runs r ON r.session_id = s.id
               GROUP BY s.id
               ORDER BY s.created_at DESC"""
        ).fetchall()
        return [dict(r) for r in rows]


def get_session(session_id: int, db_path: Path = DB_PATH) -> Optional[dict]:
    with _conn(db_path) as c:
        row = c.execute(
            "SELECT * FROM sessions WHERE id = ?", (session_id,)
        ).fetchone()
        return dict(row) if row else None


def get_session_runs(session_id: int, db_path: Path = DB_PATH) -> list[dict]:
    with _conn(db_path) as c:
        rows = c.execute(
            "SELECT * FROM runs WHERE session_id=? ORDER BY run_number",
            (session_id,),
        ).fetchall()
        return [dict(r) for r in rows]


def get_run(run_id: int, db_path: Path = DB_PATH) -> Optional[dict]:
    with _conn(db_path) as c:
        row = c.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
        return dict(row) if row else None


def get_run_actions(run_id: int, db_path: Path = DB_PATH) -> list[dict]:
    with _conn(db_path) as c:
        rows = c.execute(
            "SELECT * FROM action_results WHERE run_id=? ORDER BY action_index",
            (run_id,),
        ).fetchall()
        return [dict(r) for r in rows]


def get_label_stats(session_id: int, db_path: Path = DB_PATH) -> list[dict]:
    """Stats par label à travers tous les runs d'une session, avec app_name."""
    with _conn(db_path) as c:
        rows = c.execute(
            """SELECT
                  ar.label,
                  ar.action_type,
                  MAX(ar.app_name)                                       AS app_name,
                  COUNT(*)                                               AS run_count,
                  ROUND(AVG(ar.response_time_ms), 1)                    AS avg_ms,
                  ROUND(MAX(ar.response_time_ms), 1)                    AS max_ms,
                  ROUND(MIN(ar.response_time_ms), 1)                    AS min_ms,
                  ROUND(
                      SUM(CASE WHEN ar.status='ok' THEN 1.0 ELSE 0 END)
                      * 100.0 / COUNT(*), 1
                  )                                                      AS success_rate
               FROM action_results ar
               JOIN runs r ON ar.run_id = r.id
               WHERE r.session_id = ?
               GROUP BY ar.label, ar.action_type
               ORDER BY avg_ms DESC""",
            (session_id,),
        ).fetchall()
        return [dict(r) for r in rows]


def get_hourly_stats(session_id: int,
                     label: Optional[str] = None,
                     db_path: Path = DB_PATH) -> list[dict]:
    """Temps de réponse moyen par heure de la journée (0–23)."""
    where = "WHERE r.session_id = ?"
    params: list = [session_id]
    if label:
        where += " AND ar.label = ?"
        params.append(label)
    with _conn(db_path) as c:
        rows = c.execute(
            f"""SELECT
                   CAST(SUBSTR(ar.replayed_at, 12, 2) AS INTEGER) AS hour,
                   COUNT(*)                                        AS count,
                   ROUND(AVG(ar.response_time_ms), 1)             AS avg_ms,
                   ROUND(MAX(ar.response_time_ms), 1)             AS max_ms
                FROM action_results ar
                JOIN runs r ON ar.run_id = r.id
                {where}
                GROUP BY hour
                ORDER BY hour""",
            params,
        ).fetchall()
        return [dict(r) for r in rows]


def get_run_trend(session_id: int, label: Optional[str] = None,
                  db_path: Path = DB_PATH) -> list[dict]:
    """Évolution du temps de réponse par run (pour graphique tendance)."""
    where = "WHERE r.session_id = ?"
    params: list = [session_id]
    if label:
        where += " AND ar.label = ?"
        params.append(label)
    with _conn(db_path) as c:
        rows = c.execute(
            f"""SELECT
                   r.run_number,
                   r.started_at,
                   ROUND(AVG(ar.response_time_ms), 1) AS avg_ms,
                   ROUND(MAX(ar.response_time_ms), 1) AS max_ms,
                   SUM(CASE WHEN ar.status='ok' THEN 1 ELSE 0 END)*100/COUNT(*) AS success_rate
                FROM action_results ar
                JOIN runs r ON ar.run_id = r.id
                {where}
                GROUP BY r.id
                ORDER BY r.run_number""",
            params,
        ).fetchall()
        return [dict(r) for r in rows]


# ─── Export CSV ───────────────────────────────────────────────────────────────

def export_csv(session_id: int, db_path: Path = DB_PATH) -> str:
    with _conn(db_path) as c:
        rows = c.execute(
            """SELECT
                  s.scenario_name,
                  r.run_number,
                  r.started_at       AS run_started_at,
                  r.total_duration_s,
                  r.app_response_ms,
                  ar.action_index,
                  ar.action_type,
                  ar.label,
                  ar.app_name,
                  ar.x,
                  ar.y,
                  ar.response_time_ms,
                  ar.ocr_score,
                  ar.status,
                  ar.error_msg,
                  ar.replayed_at
               FROM action_results ar
               JOIN runs r ON ar.run_id = r.id
               JOIN sessions s ON r.session_id = s.id
               WHERE r.session_id = ?
               ORDER BY r.run_number, ar.action_index""",
            (session_id,),
        ).fetchall()

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([
        "scenario_name", "run_number", "run_started_at",
        "total_duration_s", "app_response_ms",
        "action_index", "action_type", "label", "app_name",
        "x", "y", "response_time_ms", "ocr_score",
        "status", "error_msg", "replayed_at",
    ])
    for row in rows:
        writer.writerow(list(row))
    return buf.getvalue()
