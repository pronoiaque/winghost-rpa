"""
store.py — Persistance SQLite des mesures (Time-slot store, horodatage UTC).

Deux tables :

    runs            une exécution de scénario (statut, plage horaire, total)
    action_metrics  une mesure par action (temps de réponse, ancrage…)

Tout horodatage est stocké en UTC (ISO 8601) ; la plage horaire (`time_slot`)
est dérivée à l'enregistrement pour permettre l'agrégation « 08h-09h », « 12h »…
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path

from winmonitor import config

_SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    scenario     TEXT NOT NULL,
    started_at   TEXT NOT NULL,           -- ISO 8601 UTC
    time_slot    TEXT NOT NULL,
    status       TEXT NOT NULL,           -- ok | degraded | failed
    total_ms     REAL NOT NULL,
    n_actions    INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS action_metrics (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id       INTEGER NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    action_index INTEGER NOT NULL,
    type         TEXT NOT NULL,
    response_ms  REAL NOT NULL,
    stable       INTEGER NOT NULL,
    anchored     INTEGER NOT NULL,
    confidence   REAL NOT NULL,
    status       TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_runs_scenario_slot ON runs(scenario, time_slot);
CREATE INDEX IF NOT EXISTS idx_runs_started ON runs(started_at);
"""


class MetricsStore:
    """Façade SQLite des mesures KPI."""

    def __init__(self, db_path: Path | None = None) -> None:
        self.db_path = Path(db_path or config.DB_PATH)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    @contextmanager
    def _conn(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _init_schema(self) -> None:
        with self._conn() as conn:
            conn.executescript(_SCHEMA)

    # ─── Écriture ──────────────────────────────────────────────────────────────
    def insert_run(self, result) -> int:
        """Persiste un `RunResult` (run + métriques par action). Renvoie run_id."""
        with self._conn() as conn:
            cur = conn.execute(
                "INSERT INTO runs (scenario, started_at, time_slot, status, total_ms, n_actions) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    result.scenario,
                    result.started_at,
                    result.time_slot,
                    result.status,
                    result.total_response_ms,
                    len(result.outcomes),
                ),
            )
            run_id = cur.lastrowid
            conn.executemany(
                "INSERT INTO action_metrics "
                "(run_id, action_index, type, response_ms, stable, anchored, confidence, status) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    (
                        run_id, o.index, o.type, o.response_ms,
                        int(o.stable), int(o.anchored), o.anchor_confidence, o.status,
                    )
                    for o in result.outcomes
                ],
            )
            return run_id

    # ─── Lecture ───────────────────────────────────────────────────────────────
    def runs_for(self, scenario: str | None = None, limit: int = 500) -> list[sqlite3.Row]:
        q = "SELECT * FROM runs"
        params: tuple = ()
        if scenario:
            q += " WHERE scenario = ?"
            params = (scenario,)
        q += " ORDER BY started_at DESC LIMIT ?"
        params = params + (limit,)
        with self._conn() as conn:
            return list(conn.execute(q, params))

    def scenarios(self) -> list[str]:
        with self._conn() as conn:
            rows = conn.execute("SELECT DISTINCT scenario FROM runs ORDER BY scenario")
            return [r["scenario"] for r in rows]

    def response_times(self, scenario: str, time_slot: str | None = None) -> list[float]:
        """Liste des total_ms d'un scénario (filtrable par plage horaire)."""
        q = "SELECT total_ms FROM runs WHERE scenario = ? AND status != 'failed'"
        params: tuple = (scenario,)
        if time_slot:
            q += " AND time_slot = ?"
            params += (time_slot,)
        with self._conn() as conn:
            return [r["total_ms"] for r in conn.execute(q, params)]

    def runs_between(self, start_iso: str, end_iso: str) -> list[sqlite3.Row]:
        with self._conn() as conn:
            return list(
                conn.execute(
                    "SELECT * FROM runs WHERE started_at >= ? AND started_at < ? "
                    "ORDER BY started_at",
                    (start_iso, end_iso),
                )
            )
