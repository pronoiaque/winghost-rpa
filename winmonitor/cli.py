"""
cli.py — Point d'entrée en ligne de commande de WinGhost Monitor.

Sous-commandes :

    record   <nom>        enregistre un scénario (souris/clavier, ÉCHAP pour finir)
    replay   <nom>        rejoue un scénario, mesure et stocke les temps de réponse
    list                  liste les scénarios connus
    schedule              lance le planificateur (plages horaires + rapport quotidien)
    dashboard             (re)génère le tableau de bord HTML
    report   [AAAA-MM-JJ] génère le rapport quotidien (jour courant par défaut)
    fetch-chartjs         télécharge Chart.js pour un dashboard hors-ligne
"""

from __future__ import annotations

import argparse
import sys

from version import __version__
from winmonitor import config


def _cmd_record(args) -> int:
    from winmonitor.recorder.listener import Recorder

    config.ensure_dirs()
    rec = Recorder(args.name)
    print(f"● Enregistrement « {args.name} » — agissez, puis ÉCHAP pour terminer.")
    rec.start(config.SCENARIOS_DIR)
    path = rec.save(config.SCENARIOS_DIR)
    print(f"✔ Scénario enregistré : {path}")
    return 0


def _cmd_replay(args) -> int:
    from winmonitor.scheduler.runner import run_scenario_once

    config.ensure_dirs()
    result = run_scenario_once(args.name, rebuild_dashboard=not args.no_dashboard)
    print(f"✔ Rejeu « {result.scenario} » [{result.time_slot}] — statut={result.status}")
    print(f"  Temps de réponse total : {result.total_response_ms:.0f} ms "
          f"sur {len(result.outcomes)} action(s)")
    for o in result.outcomes:
        flag = "🔍" if o.anchored else "📌"
        print(f"   #{o.index:<3} {o.type:<12} {o.response_ms:>8.0f} ms  "
              f"{flag} conf={o.anchor_confidence:.2f}  [{o.status}]")
    return 0 if result.status != "failed" else 2


def _cmd_list(_args) -> int:
    base = config.SCENARIOS_DIR
    names = sorted(p.name for p in base.iterdir()
                   if (p / "scenario.json").exists()) if base.exists() else []
    if not names:
        print("Aucun scénario. Utilisez : winmonitor record <nom>")
        return 0
    for n in names:
        print(f"• {n}")
    return 0


def _cmd_schedule(args) -> int:
    from winmonitor.scheduler.runner import MonitorScheduler

    sched = MonitorScheduler(report_hour=args.report_hour)
    if not sched.scenarios:
        print("Aucun scénario à planifier.")
        return 1
    print(f"⏰ Planification de {len(sched.scenarios)} scénario(s) par plage horaire.")
    print("   Ctrl+C pour arrêter.")
    sched.start(blocking=True)
    return 0


def _cmd_dashboard(_args) -> int:
    from winmonitor.kpi.dashboard import build_dashboard

    path = build_dashboard()
    print(f"✔ Dashboard généré : {path}")
    return 0


def _cmd_report(args) -> int:
    from winmonitor.scheduler.report import build_daily_report

    path = build_daily_report(args.date)
    print(f"✔ Rapport généré : {path}")
    return 0


def _cmd_fetch_chartjs(_args) -> int:
    from winmonitor.kpi.fetch_chartjs import fetch

    path = fetch()
    print(f"✔ Chart.js téléchargé : {path}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="winmonitor",
                                description="WinGhost Monitor — supervision de performance applicative")
    p.add_argument("--version", action="version", version=f"WinGhost Monitor {__version__}")
    sub = p.add_subparsers(dest="command", required=True)

    pr = sub.add_parser("record", help="enregistrer un scénario")
    pr.add_argument("name")
    pr.set_defaults(func=_cmd_record)

    pl = sub.add_parser("replay", help="rejouer un scénario et mesurer")
    pl.add_argument("name")
    pl.add_argument("--no-dashboard", action="store_true")
    pl.set_defaults(func=_cmd_replay)

    sub.add_parser("list", help="lister les scénarios").set_defaults(func=_cmd_list)

    ps = sub.add_parser("schedule", help="lancer le planificateur")
    ps.add_argument("--report-hour", type=int, default=20)
    ps.set_defaults(func=_cmd_schedule)

    sub.add_parser("dashboard", help="(re)générer le dashboard").set_defaults(func=_cmd_dashboard)

    prep = sub.add_parser("report", help="générer le rapport quotidien")
    prep.add_argument("date", nargs="?", default=None, help="AAAA-MM-JJ (défaut: aujourd'hui)")
    prep.set_defaults(func=_cmd_report)

    sub.add_parser("fetch-chartjs", help="télécharger Chart.js (hors-ligne)").set_defaults(
        func=_cmd_fetch_chartjs)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
