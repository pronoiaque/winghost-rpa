"""
runner.py — Orchestration temporelle (APScheduler).

Déclenche chaque scénario au début de chaque plage horaire (cf. TIME_SLOTS),
enchaîne : rejeu (Couche 2) → mesure (Couche 3) → persistance SQLite →
régénération du dashboard. Un job quotidien produit le rapport agrégé.

`run_scenario_once` est aussi utilisable seul (CLI `replay`) sans planificateur.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from winmonitor import config
from winmonitor.kpi.dashboard import build_dashboard
from winmonitor.kpi.store import MetricsStore
from winmonitor.recorder.scenario import Scenario
from winmonitor.replayer.replayer import Replayer, RunResult


def run_scenario_once(name: str, store: MetricsStore | None = None,
                      rebuild_dashboard: bool = True) -> RunResult:
    """Rejoue un scénario, persiste les mesures, régénère le dashboard."""
    store = store or MetricsStore()
    folder = Scenario.folder_for(config.SCENARIOS_DIR, name)
    scenario = Scenario.load(folder)
    result = Replayer().run(scenario, folder)
    store.insert_run(result)
    if rebuild_dashboard:
        build_dashboard(store)
    return result


def _discover_scenarios() -> list[str]:
    base = config.SCENARIOS_DIR
    if not base.exists():
        return []
    return sorted(p.name for p in base.iterdir() if (p / "scenario.json").exists())


class MonitorScheduler:
    """Planificateur APScheduler : scénarios par plage + rapport quotidien."""

    def __init__(self, scenarios: list[str] | None = None,
                 report_hour: int = 20) -> None:
        self.scenarios = scenarios or _discover_scenarios()
        self.report_hour = report_hour
        self.store = MetricsStore()
        self._scheduler = None

    def _build(self):
        from apscheduler.schedulers.background import BackgroundScheduler
        from apscheduler.triggers.cron import CronTrigger

        sched = BackgroundScheduler(timezone=str(datetime.now().astimezone().tzinfo))
        # Un déclenchement par scénario au début de chaque plage horaire.
        start_hours = sorted({start for label, start, _ in config.TIME_SLOTS
                              if label != "hors-plage"})
        for name in self.scenarios:
            for hour in start_hours:
                sched.add_job(
                    run_scenario_once, CronTrigger(hour=hour, minute=0),
                    args=[name, self.store], id=f"{name}@{hour}",
                    misfire_grace_time=300, replace_existing=True,
                )
        # Rapport quotidien.
        sched.add_job(
            build_daily_report_job, CronTrigger(hour=self.report_hour, minute=0),
            id="daily_report", replace_existing=True,
        )
        return sched

    def start(self, blocking: bool = True) -> None:
        config.ensure_dirs()
        self._scheduler = self._build()
        self._scheduler.start()
        if blocking:
            import time

            try:
                while True:
                    time.sleep(1)
            except (KeyboardInterrupt, SystemExit):
                self.stop()

    def stop(self) -> None:
        if self._scheduler is not None:
            self._scheduler.shutdown(wait=False)
            self._scheduler = None

    def jobs(self) -> list:
        return self._scheduler.get_jobs() if self._scheduler else []


def build_daily_report_job() -> None:
    """Job APScheduler : rapport du jour courant."""
    from winmonitor.scheduler.report import build_daily_report

    build_daily_report(datetime.now(timezone.utc).date().isoformat())
