"""
report.py — Rapport quotidien agrégé (résultats → SQLite → agrégation → rapport).

Pour une date donnée, agrège toutes les exécutions par scénario et par plage
horaire (médiane, p95, taux de succès) et écrit un rapport HTML léger +
un résumé Markdown dans REPORTS_DIR.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

from winmonitor import config
from winmonitor.kpi.baseline import _percentile, median
from winmonitor.kpi.store import MetricsStore


def _day_bounds_utc(day_iso: str) -> tuple[str, str]:
    start = datetime.fromisoformat(day_iso).replace(tzinfo=timezone.utc)
    end = start + timedelta(days=1)
    return start.isoformat(), end.isoformat()


def aggregate(day_iso: str, store: MetricsStore | None = None) -> dict:
    """Agrège les runs du jour par (scénario, plage horaire)."""
    store = store or MetricsStore()
    start_iso, end_iso = _day_bounds_utc(day_iso)
    rows = store.runs_between(start_iso, end_iso)

    buckets: dict[tuple[str, str], list] = defaultdict(list)
    for r in rows:
        buckets[(r["scenario"], r["time_slot"])].append(r)

    summary = []
    for (scenario, slot), runs in sorted(buckets.items()):
        oks = [x for x in runs if x["status"] != "failed"]
        times = [x["total_ms"] for x in oks]
        summary.append(
            {
                "scenario": scenario,
                "time_slot": slot,
                "runs": len(runs),
                "success": len(oks),
                "success_rate": round(100 * len(oks) / len(runs), 1) if runs else 0.0,
                "median_ms": round(median(times), 1) if times else 0.0,
                "p95_ms": round(_percentile(times, 0.95), 1) if times else 0.0,
            }
        )
    return {"date": day_iso, "rows": summary, "total_runs": len(rows)}


def build_daily_report(day_iso: str | None = None,
                       store: MetricsStore | None = None) -> Path:
    """Génère le rapport du jour (HTML + Markdown) et renvoie le chemin HTML."""
    day_iso = day_iso or datetime.now(timezone.utc).date().isoformat()
    data = aggregate(day_iso, store)
    config.REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    rows_html = "\n".join(
        f"<tr><td>{r['scenario']}</td><td>{r['time_slot']}</td>"
        f"<td>{r['runs']}</td><td>{r['success_rate']} %</td>"
        f"<td>{r['median_ms']}</td><td>{r['p95_ms']}</td></tr>"
        for r in data["rows"]
    ) or '<tr><td colspan="6">Aucune exécution ce jour.</td></tr>'

    html = f"""<!DOCTYPE html><html lang="fr"><head><meta charset="utf-8">
<title>Rapport quotidien — {day_iso}</title>
<style>body{{font-family:Segoe UI,sans-serif;margin:24px;color:#1f2937}}
table{{border-collapse:collapse;width:100%}}th,td{{border-bottom:1px solid #e5e7eb;
padding:6px 10px;text-align:left;font-size:13px}}th{{background:#eef2ff}}</style></head>
<body><h1>Rapport quotidien — {day_iso}</h1>
<p>{data['total_runs']} exécution(s) au total.</p>
<table><thead><tr><th>Scénario</th><th>Plage</th><th>Exéc.</th>
<th>Succès</th><th>Médiane (ms)</th><th>p95 (ms)</th></tr></thead>
<tbody>{rows_html}</tbody></table></body></html>"""

    md_lines = [f"# Rapport quotidien — {day_iso}", "",
                f"{data['total_runs']} exécution(s).", "",
                "| Scénario | Plage | Exéc. | Succès | Médiane (ms) | p95 (ms) |",
                "|---|---|---|---|---|---|"]
    for r in data["rows"]:
        md_lines.append(
            f"| {r['scenario']} | {r['time_slot']} | {r['runs']} | "
            f"{r['success_rate']} % | {r['median_ms']} | {r['p95_ms']} |"
        )

    html_path = config.REPORTS_DIR / f"report_{day_iso}.html"
    md_path = config.REPORTS_DIR / f"report_{day_iso}.md"
    html_path.write_text(html, encoding="utf-8")
    md_path.write_text("\n".join(md_lines) + "\n", encoding="utf-8")
    return html_path
