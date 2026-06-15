"""
dashboard.py — Génère un tableau de bord HTML autonome (Chart.js embarqué).

Le HTML produit est 100 % statique et fonctionne hors-ligne (poste CHU sans
Internet) : les données sont sérialisées en JSON DANS la page, et Chart.js est
chargé depuis un fichier voisin `chart.umd.min.js`. Récupérer ce fichier une
seule fois via `python -m winmonitor.kpi.fetch_chartjs` ; en son absence, la
page bascule automatiquement sur un rendu SVG minimal sans dépendance.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from winmonitor import config
from winmonitor.kpi.baseline import compute_baseline
from winmonitor.kpi.store import MetricsStore

_PAGE = """<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>WinGhost Monitor — Performances CHU</title>
<style>
  body {{ font-family: Segoe UI, Roboto, sans-serif; margin: 0; background:#f4f6fb; color:#1f2937; }}
  header {{ background:#4338ca; color:#fff; padding:18px 28px; }}
  header h1 {{ margin:0; font-size:20px; }}
  header .sub {{ opacity:.85; font-size:13px; margin-top:4px; }}
  .grid {{ padding:24px; display:grid; gap:24px; grid-template-columns:repeat(auto-fit,minmax(460px,1fr)); }}
  .card {{ background:#fff; border-radius:12px; box-shadow:0 1px 3px rgba(0,0,0,.08); padding:18px 20px; }}
  .card h2 {{ margin:0 0 4px; font-size:15px; }}
  .card .meta {{ font-size:12px; color:#6b7280; margin-bottom:12px; }}
  .pill {{ display:inline-block; padding:2px 8px; border-radius:999px; font-size:11px; font-weight:600; }}
  .ok {{ background:#dcfce7; color:#166534; }}
  .degraded {{ background:#fef9c3; color:#854d0e; }}
  .failed {{ background:#fee2e2; color:#991b1b; }}
  footer {{ padding:16px 28px; font-size:12px; color:#6b7280; }}
  table {{ width:100%; border-collapse:collapse; font-size:12px; }}
  th,td {{ text-align:left; padding:4px 6px; border-bottom:1px solid #eef0f4; }}
</style>
</head>
<body>
<header>
  <h1>WinGhost Monitor — Performances applicatives CHU</h1>
  <div class="sub">v{version} · généré le {generated} · {n_scen} scénario(s) · base SQLite</div>
</header>
<div class="grid" id="grid"></div>
<footer>Temps de réponse = chronomètre visuel (t_action → écran stable). Baseline = médiane / p95 historiques par plage horaire.</footer>

<script>
const DATA = {data_json};
</script>
<script src="chart.umd.min.js" onerror="window.__noChart=true"></script>
<script>
{render_js}
</script>
</body>
</html>
"""

# Rendu : Chart.js si présent, sinon repli SVG minimal (zéro dépendance).
_RENDER_JS = r"""
function slotBadge(status){return '<span class="pill '+status+'">'+status+'</span>';}

function makeCard(scen){
  const card=document.createElement('div'); card.className='card';
  const last=scen.points.length?scen.points[scen.points.length-1]:null;
  card.innerHTML='<h2>'+scen.name+' '+(last?slotBadge(last.status):'')+'</h2>'+
    '<div class="meta">médiane '+scen.baseline.median_ms+' ms · p95 '+scen.baseline.p95_ms+
    ' ms · '+scen.points.length+' exécution(s)</div>';
  const canvas=document.createElement('canvas'); canvas.height=200; card.appendChild(canvas);
  document.getElementById('grid').appendChild(card);
  drawChart(canvas,scen);
}

function drawChart(canvas,scen){
  const labels=scen.points.map(p=>p.label);
  const values=scen.points.map(p=>p.total_ms);
  if(!window.__noChart && window.Chart){
    new Chart(canvas,{type:'line',data:{labels,datasets:[
      {label:'temps de réponse (ms)',data:values,borderColor:'#4338ca',
       backgroundColor:'rgba(67,56,202,.12)',fill:true,tension:.25,pointRadius:2},
      {label:'p95 baseline',data:values.map(()=>scen.baseline.p95_ms),
       borderColor:'#f59e0b',borderDash:[6,4],pointRadius:0,fill:false},
    ]},options:{plugins:{legend:{labels:{boxWidth:12,font:{size:11}}}},
      scales:{y:{beginAtZero:true,title:{display:true,text:'ms'}}}}});
  } else {
    canvas.replaceWith(svgFallback(values,scen.baseline.p95_ms));
  }
}

function svgFallback(values,p95){
  const W=420,H=200,pad=28; const max=Math.max(p95,...values,1);
  const xs=i=>pad+(W-2*pad)*(values.length<2?0:i/(values.length-1));
  const ys=v=>H-pad-(H-2*pad)*(v/max);
  let pts=values.map((v,i)=>xs(i)+','+ys(v)).join(' ');
  const yb=ys(p95);
  const div=document.createElement('div');
  div.innerHTML='<svg width="100%" viewBox="0 0 '+W+' '+H+'">'+
    '<polyline fill="none" stroke="#4338ca" stroke-width="2" points="'+pts+'"/>'+
    '<line x1="'+pad+'" y1="'+yb+'" x2="'+(W-pad)+'" y2="'+yb+'" stroke="#f59e0b" stroke-dasharray="6 4"/>'+
    '<text x="'+pad+'" y="14" font-size="11" fill="#6b7280">max '+Math.round(max)+' ms · p95 '+p95+' ms</text>'+
    '</svg>';
  return div;
}

DATA.scenarios.forEach(makeCard);
"""


def _local_iso(iso_utc: str) -> str:
    """Convertit un ISO UTC en libellé court heure locale pour l'axe X."""
    try:
        dt = datetime.fromisoformat(iso_utc)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone().strftime("%d/%m %H:%M")
    except Exception:
        return iso_utc[:16]


def build_dashboard(store: MetricsStore | None = None, out_dir: Path | None = None) -> Path:
    """Génère index.html dans DASHBOARD_DIR et renvoie son chemin."""
    from version import __version__

    store = store or MetricsStore()
    out_dir = Path(out_dir or config.DASHBOARD_DIR)
    out_dir.mkdir(parents=True, exist_ok=True)

    scenarios = []
    for name in store.scenarios():
        runs = list(reversed(store.runs_for(name, limit=200)))  # chronologique
        baseline = compute_baseline(store, name)
        scenarios.append(
            {
                "name": name,
                "baseline": {"median_ms": baseline.median_ms, "p95_ms": baseline.p95_ms},
                "points": [
                    {
                        "label": _local_iso(r["started_at"]),
                        "total_ms": round(r["total_ms"], 1),
                        "status": r["status"],
                    }
                    for r in runs
                ],
            }
        )

    html = _PAGE.format(
        version=__version__,
        generated=datetime.now().strftime("%Y-%m-%d %H:%M"),
        n_scen=len(scenarios),
        data_json=json.dumps({"scenarios": scenarios}, ensure_ascii=False),
        render_js=_RENDER_JS,
    )
    path = out_dir / "index.html"
    path.write_text(html, encoding="utf-8")
    return path
