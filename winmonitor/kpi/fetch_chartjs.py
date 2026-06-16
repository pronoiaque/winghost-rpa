"""
fetch_chartjs.py — Télécharge Chart.js (UMD) à côté du dashboard, une seule fois.

Usage (sur un poste AVEC Internet, avant déploiement CHU) :

    python -m winmonitor.kpi.fetch_chartjs

Le fichier `chart.umd.min.js` est déposé dans DASHBOARD_DIR. Une fois présent,
le tableau de bord fonctionne 100 % hors-ligne. En son absence, le dashboard
bascule automatiquement sur un rendu SVG minimal (cf. dashboard.py).
"""

from __future__ import annotations

from pathlib import Path

from winmonitor import config

_CHARTJS_URL = "https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"


def fetch(out_dir: Path | None = None) -> Path:
    import urllib.request

    out_dir = Path(out_dir or config.DASHBOARD_DIR)
    out_dir.mkdir(parents=True, exist_ok=True)
    dest = out_dir / "chart.umd.min.js"
    with urllib.request.urlopen(_CHARTJS_URL, timeout=30) as resp:
        dest.write_bytes(resp.read())
    return dest


if __name__ == "__main__":
    path = fetch()
    print(f"Chart.js téléchargé : {path} ({path.stat().st_size // 1024} Ko)")
