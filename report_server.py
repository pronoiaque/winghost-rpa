"""
report_server.py — Dashboard web dynamique WinGhost RPA v3.

Lance un serveur Flask local qui expose :
  GET  /                              → liste de toutes les sessions enregistrées
  GET  /session/<id>                  → détail : runs, stats par label, heatmap horaire
  GET  /run/<id>                      → détail d'un run (actions + screenshots)
  GET  /api/session/<id>/export.csv   → export CSV brut
  GET  /api/session/<id>/data         → données JSON pour rechargement AJAX

Usage :
  python report_server.py              # port 5000 par défaut
  python report_server.py --port=8080

Thème dark cohérent avec l'interface Tkinter (même palette CSS).
Graphiques Chart.js (nécessite une connexion Internet ou remplacez par le CDN local).
"""

import argparse
import json
import sys
from pathlib import Path

try:
    from flask import Flask, Response, abort, jsonify, redirect, url_for
except ImportError:
    print("Flask requis : pip install flask", file=sys.stderr)
    sys.exit(1)

import stats_db

app = Flask(__name__)
app.config["JSON_SORT_KEYS"] = False

# ─── Palette (cohérente avec gui.py) ─────────────────────────────────────────

_CSS = """
:root{--bg:#1C1F26;--bg2:#252932;--bg3:#2E3440;--bg4:#353B4A;
      --accent:#5E9BF0;--accent2:#F0965E;--green:#4EC9A0;
      --red:#E06C75;--yellow:#E5C07B;--fg:#D8DEE9;--fg2:#7B8496;
      --font:'Segoe UI',system-ui,sans-serif;--mono:Consolas,monospace}
*{box-sizing:border-box;margin:0;padding:0}
html,body{height:100%}
body{background:var(--bg);color:var(--fg);font-family:var(--font);font-size:14px}
a{color:var(--accent);text-decoration:none}a:hover{text-decoration:underline}
/* nav */
nav{background:var(--bg2);padding:12px 28px;display:flex;align-items:center;
    gap:16px;border-bottom:1px solid var(--bg3);position:sticky;top:0;z-index:100}
nav .brand{font-size:16px;font-weight:700;color:var(--accent)}
nav .breadcrumb{color:var(--fg2);font-size:13px}
nav .breadcrumb a{color:var(--fg2)}nav .breadcrumb span{color:var(--fg)}
/* page */
.page{padding:28px 32px}
h1{font-size:20px;color:var(--accent);margin-bottom:6px}
h2{font-size:15px;color:var(--accent2);margin:24px 0 10px}
.subtitle{color:var(--fg2);font-size:12px;margin-bottom:20px}
/* cards */
.cards{display:flex;gap:12px;flex-wrap:wrap;margin-bottom:24px}
.card{background:var(--bg2);border-radius:8px;padding:14px 20px;min-width:120px}
.card .val{font-size:26px;font-weight:700}.card .lbl{font-size:11px;color:var(--fg2);margin-top:2px}
.card.ok .val{color:var(--green)}.card.warn .val{color:var(--yellow)}
.card.err .val{color:var(--red)}.card.blue .val{color:var(--accent)}
.card.orange .val{color:var(--accent2)}
/* tables */
.tbl-wrap{background:var(--bg2);border-radius:8px;overflow:auto;margin-bottom:24px}
table{border-collapse:collapse;width:100%;font-size:12px}
th{background:var(--bg3);color:var(--accent);font-weight:600;padding:8px 12px;
   text-align:left;white-space:nowrap;position:sticky;top:0}
td{padding:7px 12px;border-bottom:1px solid var(--bg3);vertical-align:middle}
tr:hover td{background:var(--bg4)}
td.ok{color:var(--green)}td.err{color:var(--red)}td.warn{color:var(--yellow)}
td.mono{font-family:var(--mono)}td.label{color:var(--accent2)}
/* chart */
.chart-box{background:var(--bg2);border-radius:8px;padding:20px;margin-bottom:24px}
.chart-box h2{margin-top:0}
/* badge */
.badge{display:inline-block;padding:2px 7px;border-radius:4px;font-size:11px;font-weight:600}
.badge-ok{background:#1d3d31;color:var(--green)}
.badge-skip{background:#3d3520;color:var(--yellow)}
.badge-err{background:#3d1f22;color:var(--red)}
/* screenshot */
.ss-thumb{height:52px;width:auto;border-radius:4px;border:1px solid var(--bg3);
          cursor:zoom-in;transition:transform .15s}
.ss-thumb:hover{transform:scale(4);z-index:20;position:relative;box-shadow:0 4px 20px #000a}
/* btn */
.btn{display:inline-block;padding:7px 14px;border-radius:6px;font-size:13px;
     cursor:pointer;border:none;font-family:var(--font);text-decoration:none!important}
.btn-primary{background:var(--accent);color:#11141a}
.btn-secondary{background:var(--bg3);color:var(--fg2)}
.btn-secondary:hover{background:var(--bg4);color:var(--fg)}
.btn-green{background:var(--green);color:#0d1f1a}
.actions-bar{display:flex;gap:8px;margin-bottom:20px;align-items:center}
/* empty */
.empty{padding:40px;text-align:center;color:var(--fg2)}
"""

_CHARTJS_CDN = "https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"


def _page(title: str, body: str, breadcrumb: str = "") -> str:
    bc = (f'<span class="breadcrumb">{breadcrumb}</span>' if breadcrumb else "")
    return f"""<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title} — WinGhost RPA</title>
<style>{_CSS}</style>
<script src="{_CHARTJS_CDN}"></script>
</head>
<body>
<nav>
  <a class="brand" href="/">🤖 WinGhost RPA</a>
  {bc}
</nav>
<div class="page">{body}</div>
</body>
</html>"""


def _badge(status: str) -> str:
    cls = {"ok": "badge-ok", "skip": "badge-skip", "error": "badge-err"}.get(status, "badge-skip")
    label = {"ok": "✔ OK", "skip": "⚠ Ignoré", "error": "✘ Erreur"}.get(status, status)
    return f'<span class="badge {cls}">{label}</span>'


def _fmt_ms(ms) -> str:
    if ms is None:
        return "—"
    return f"{ms:.0f} ms"


def _fmt_dt(iso: str) -> str:
    if not iso:
        return "—"
    return iso.replace("T", " ").split(".")[0]


# ─── Routes ───────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    stats_db.init_db()
    sessions = stats_db.get_all_sessions()

    if not sessions:
        body = """
        <h1>Sessions enregistrées</h1>
        <div class="empty">
          Aucune session n'a encore été rejoué avec persistance DB.<br>
          Lancez l'interface WinGhost RPA, effectuez un replay puis revenez ici.
        </div>"""
        return _page("Accueil", body)

    rows = ""
    for s in sessions:
        avg = _fmt_ms(s.get("global_avg_ms"))
        last = _fmt_dt(s.get("last_run_at") or "")
        rows += (
            f'<tr>'
            f'<td><a href="/session/{s["id"]}">{s["name"]}</a></td>'
            f'<td class="mono">{s["action_count"]}</td>'
            f'<td class="mono">{s.get("run_count", 0)}</td>'
            f'<td class="mono">{avg}</td>'
            f'<td class="mono">{last}</td>'
            f'<td><a class="btn btn-secondary" href="/session/{s["id"]}">Détails</a>'
            f' &nbsp;<a class="btn btn-secondary" href="/api/session/{s["id"]}/export.csv" download>CSV</a></td>'
            f'</tr>\n'
        )

    body = f"""
<h1>Sessions enregistrées</h1>
<div class="subtitle">{len(sessions)} session(s) dans la base de données locale.</div>
<div class="tbl-wrap">
<table>
  <thead><tr>
    <th>Session</th><th>Actions</th><th>Runs</th>
    <th>Avg réponse</th><th>Dernier run</th><th>Actions</th>
  </tr></thead>
  <tbody>{rows}</tbody>
</table>
</div>"""
    return _page("Accueil", body)


@app.route("/session/<int:session_id>")
def session_detail(session_id: int):
    stats_db.init_db()
    session = stats_db.get_session(session_id)
    if not session:
        abort(404)

    runs        = stats_db.get_session_runs(session_id)
    label_stats = stats_db.get_label_stats(session_id)
    hourly      = stats_db.get_hourly_stats(session_id)
    trend       = stats_db.get_run_trend(session_id)

    # Cartes résumé
    total_runs   = len(runs)
    last_ok      = sum(1 for r in runs if r.get("ok_count", 0) == r.get("total", 0) and r.get("total", 0) > 0)
    all_avg_ms   = [r["avg_response_ms"] for r in runs if r.get("avg_response_ms") is not None]
    global_avg   = round(sum(all_avg_ms) / len(all_avg_ms), 1) if all_avg_ms else None

    cards = f"""
<div class="cards">
  <div class="card blue"><div class="val">{total_runs}</div><div class="lbl">Runs total</div></div>
  <div class="card ok"><div class="val">{last_ok}</div><div class="lbl">✔ Runs complets</div></div>
  <div class="card orange"><div class="val">{_fmt_ms(global_avg)}</div><div class="lbl">⏱ Avg global</div></div>
  <div class="card blue"><div class="val">{session["action_count"]}</div><div class="lbl">Actions / session</div></div>
</div>"""

    # Tableau runs
    run_rows = ""
    for r in runs:
        pct_ok = (r["ok_count"] * 100 // r["total"]) if r.get("total") else 0
        cls = "ok" if pct_ok == 100 else ("warn" if pct_ok >= 70 else "err")
        run_rows += (
            f'<tr>'
            f'<td class="mono">#{r["run_number"]}</td>'
            f'<td class="mono">{_fmt_dt(r["started_at"])}</td>'
            f'<td class="mono">{r.get("total","—")}</td>'
            f'<td class="mono {cls}">{r["ok_count"]}</td>'
            f'<td class="mono warn">{r["skip_count"]}</td>'
            f'<td class="mono err">{r["error_count"]}</td>'
            f'<td class="mono">{_fmt_ms(r.get("avg_response_ms"))}</td>'
            f'<td class="mono">{_fmt_ms(r.get("max_response_ms"))}</td>'
            f'<td><a class="btn btn-secondary" href="/run/{r["id"]}">Détail</a></td>'
            f'</tr>\n'
        )

    runs_table = f"""
<h2>Historique des runs</h2>
<div class="tbl-wrap">
<table>
  <thead><tr>
    <th>Run</th><th>Démarré le</th><th>Total</th>
    <th>✔ OK</th><th>⚠ Ignorées</th><th>✘ Erreurs</th>
    <th>Avg (ms)</th><th>Max (ms)</th><th></th>
  </tr></thead>
  <tbody>{run_rows if run_rows else '<tr><td colspan="9" class="empty">Aucun run.</td></tr>'}</tbody>
</table>
</div>"""

    # Tableau stats par label
    label_rows = ""
    for l in label_stats:
        sr = l.get("success_rate") or 0
        cls = "ok" if sr >= 95 else ("warn" if sr >= 70 else "err")
        label_rows += (
            f'<tr>'
            f'<td class="label">{l["label"] or "—"}</td>'
            f'<td class="mono">{l.get("action_type","—")}</td>'
            f'<td class="mono">{l.get("run_count","—")}</td>'
            f'<td class="mono">{_fmt_ms(l.get("avg_ms"))}</td>'
            f'<td class="mono">{_fmt_ms(l.get("max_ms"))}</td>'
            f'<td class="mono">{_fmt_ms(l.get("min_ms"))}</td>'
            f'<td class="mono {cls}">{sr:.1f}%</td>'
            f'</tr>\n'
        )

    labels_table = f"""
<h2>Temps de réponse par bouton / cible</h2>
<div class="tbl-wrap">
<table>
  <thead><tr>
    <th>Cible (label)</th><th>Type</th><th>Exécutions</th>
    <th>Avg (ms)</th><th>Max (ms)</th><th>Min (ms)</th><th>Taux OK</th>
  </tr></thead>
  <tbody>{label_rows if label_rows else '<tr><td colspan="7" class="empty">Aucune donnée.</td></tr>'}</tbody>
</table>
</div>"""

    # Graphiques (Chart.js)
    trend_labels  = json.dumps([f"#{r['run_number']}" for r in trend])
    trend_avg     = json.dumps([r.get("avg_ms") for r in trend])
    trend_max     = json.dumps([r.get("max_ms") for r in trend])
    trend_sr      = json.dumps([r.get("success_rate") for r in trend])

    hourly_labels = json.dumps([f"{r['hour']:02d}h" for r in hourly])
    hourly_avg    = json.dumps([r.get("avg_ms") for r in hourly])
    hourly_count  = json.dumps([r.get("count") for r in hourly])

    charts = f"""
<div style="display:grid;grid-template-columns:1fr 1fr;gap:16px">
  <div class="chart-box">
    <h2>Tendance avg réponse par run (ms)</h2>
    <canvas id="trendChart" height="160"></canvas>
  </div>
  <div class="chart-box">
    <h2>Heatmap horaire — avg réponse (ms)</h2>
    <canvas id="hourChart" height="160"></canvas>
  </div>
</div>
<script>
(function(){{
  const ACCENT='#5E9BF0',ACCENT2='#F0965E',GREEN='#4EC9A0',FG2='#7B8496',BG3='#2E3440';
  Chart.defaults.color=FG2;Chart.defaults.borderColor=BG3;

  new Chart(document.getElementById('trendChart'),{{
    type:'line',
    data:{{
      labels:{trend_labels},
      datasets:[
        {{label:'Avg ms',data:{trend_avg},borderColor:ACCENT,backgroundColor:ACCENT+'33',
          tension:.3,fill:true,pointRadius:4}},
        {{label:'Max ms',data:{trend_max},borderColor:ACCENT2,borderDash:[5,3],
          tension:.3,pointRadius:3,fill:false}},
      ]
    }},
    options:{{responsive:true,plugins:{{legend:{{labels:{{boxWidth:12}}}}}},
      scales:{{y:{{beginAtZero:true,title:{{display:true,text:'ms'}}}}}}}}
  }});

  new Chart(document.getElementById('hourChart'),{{
    type:'bar',
    data:{{
      labels:{hourly_labels},
      datasets:[
        {{label:'Avg ms',data:{hourly_avg},backgroundColor:ACCENT+'99',borderColor:ACCENT,borderWidth:1}},
        {{label:'Nb exécutions',data:{hourly_count},backgroundColor:GREEN+'55',
          borderColor:GREEN,borderWidth:1,yAxisID:'y2'}},
      ]
    }},
    options:{{responsive:true,plugins:{{legend:{{labels:{{boxWidth:12}}}}}},
      scales:{{
        y:{{beginAtZero:true,title:{{display:true,text:'ms'}}}},
        y2:{{position:'right',beginAtZero:true,grid:{{display:false}},
              title:{{display:true,text:'N'}}}}
      }}
    }}
  }});
}})();
</script>"""

    actions_bar = f"""
<div class="actions-bar">
  <a class="btn btn-green" href="/api/session/{session_id}/export.csv" download>
    ⬇ Export CSV
  </a>
  <a class="btn btn-secondary" href="/">← Retour</a>
</div>"""

    body = f"""
<h1>{session["name"]}</h1>
<div class="subtitle">{session["filepath"]}</div>
{actions_bar}
{cards}
{charts}
{runs_table}
{labels_table}"""

    bc = f'<a href="/">Accueil</a> › <span>{session["name"]}</span>'
    return _page(session["name"], body, bc)


@app.route("/run/<int:run_id>")
def run_detail(run_id: int):
    stats_db.init_db()
    run = stats_db.get_run(run_id)
    if not run:
        abort(404)

    session = stats_db.get_session(run["session_id"])
    actions = stats_db.get_run_actions(run_id)

    pct_ok = (run["ok_count"] * 100 // run["total"]) if run.get("total") else 0

    cards = f"""
<div class="cards">
  <div class="card blue"><div class="val">#{run["run_number"]}</div><div class="lbl">Run</div></div>
  <div class="card ok"><div class="val">{run.get("ok_count","—")}</div><div class="lbl">✔ OK</div></div>
  <div class="card warn"><div class="val">{run.get("skip_count","—")}</div><div class="lbl">⚠ Ignorées</div></div>
  <div class="card err"><div class="val">{run.get("error_count","—")}</div><div class="lbl">✘ Erreurs</div></div>
  <div class="card orange"><div class="val">{_fmt_ms(run.get("avg_response_ms"))}</div><div class="lbl">⏱ Avg</div></div>
  <div class="card warn"><div class="val">{_fmt_ms(run.get("max_response_ms"))}</div><div class="lbl">⏱ Max</div></div>
</div>"""

    rows = ""
    for a in actions:
        ss = a.get("screenshot_b64") or ""
        ss_cell = (
            f'<img class="ss-thumb" src="data:image/png;base64,{ss}" alt="screenshot">'
            if ss else "—"
        )
        rows += (
            f'<tr>'
            f'<td class="mono">{a["action_index"]}</td>'
            f'<td class="mono">{a["action_type"]}</td>'
            f'<td class="label">{a.get("label") or "—"}</td>'
            f'<td>{_badge(a.get("status","ok"))}</td>'
            f'<td class="mono">{_fmt_ms(a.get("response_time_ms"))}</td>'
            f'<td class="mono">{f"{a["ocr_score"]:.2f}" if a.get("ocr_score") is not None else "—"}</td>'
            f'<td class="mono">{"✔" if a.get("visual_ok")==1 else ("✘" if a.get("visual_ok")==0 else "—")}</td>'
            f'<td>{ss_cell}</td>'
            f'<td class="mono" style="color:var(--red);font-size:11px">{a.get("error_msg") or ""}</td>'
            f'</tr>\n'
        )

    table = f"""
<div class="tbl-wrap">
<table>
  <thead><tr>
    <th>#</th><th>Type</th><th>Cible</th><th>Statut</th>
    <th>Réponse</th><th>OCR</th><th>Visuel</th>
    <th>Screenshot</th><th>Erreur</th>
  </tr></thead>
  <tbody>{rows if rows else '<tr><td colspan="9" class="empty">Aucune action.</td></tr>'}</tbody>
</table>
</div>"""

    sname = session["name"] if session else f"session#{run['session_id']}"
    actions_bar = f"""
<div class="actions-bar">
  <a class="btn btn-secondary" href="/session/{run['session_id']}">← Session {sname}</a>
</div>"""

    body = f"""
<h1>Run #{run["run_number"]} — {sname}</h1>
<div class="subtitle">Démarré le {_fmt_dt(run["started_at"])}</div>
{actions_bar}
{cards}
<h2>Détail des actions</h2>
{table}"""

    bc = (f'<a href="/">Accueil</a> › '
          f'<a href="/session/{run["session_id"]}">{sname}</a> › '
          f'<span>Run #{run["run_number"]}</span>')
    return _page(f"Run #{run['run_number']}", body, bc)


# ─── API JSON / CSV ────────────────────────────────────────────────────────────

@app.route("/api/session/<int:session_id>/data")
def api_session_data(session_id: int):
    stats_db.init_db()
    session = stats_db.get_session(session_id)
    if not session:
        abort(404)
    return jsonify({
        "session":    session,
        "runs":       stats_db.get_session_runs(session_id),
        "labels":     stats_db.get_label_stats(session_id),
        "hourly":     stats_db.get_hourly_stats(session_id),
        "trend":      stats_db.get_run_trend(session_id),
    })


@app.route("/api/session/<int:session_id>/export.csv")
def api_export_csv(session_id: int):
    stats_db.init_db()
    session = stats_db.get_session(session_id)
    if not session:
        abort(404)
    csv_data = stats_db.export_csv(session_id)
    filename = f"{session['name']}_export.csv"
    return Response(
        csv_data,
        mimetype="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.route("/api/run/<int:run_id>/data")
def api_run_data(run_id: int):
    stats_db.init_db()
    run = stats_db.get_run(run_id)
    if not run:
        abort(404)
    actions = stats_db.get_run_actions(run_id)
    # Ne pas renvoyer les screenshots dans l'API JSON (trop volumineux)
    for a in actions:
        a.pop("screenshot_b64", None)
    return jsonify({"run": run, "actions": actions})


# ─── Lancement ────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="WinGhost RPA — Dashboard web v3")
    parser.add_argument("--port", type=int, default=5000, help="Port HTTP (défaut: 5000)")
    parser.add_argument("--host", default="127.0.0.1", help="Hôte (défaut: 127.0.0.1)")
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args()

    stats_db.init_db()
    print(f"🌐 Dashboard WinGhost RPA → http://{args.host}:{args.port}/")
    app.run(host=args.host, port=args.port, debug=args.debug)


if __name__ == "__main__":
    main()
