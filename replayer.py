"""
replayer.py — Rejoue une session enregistrée avec vérification visuelle OCR.

v2 : - ActionResult expose `label` (nom humain déduit de l'OCR enregistré)
     - save_report() génère report_*.json ET report_*.html (graphique SVG)
     - support multi-moniteurs via screenshot_region() de recorder.py

Fonctions clés :
  • Vérifie que le contexte OCR autour de chaque cible correspond à ce qui
    a été enregistré (score de similarité configurable).
  • Mesure le temps de réponse applicatif entre l'action automatisée et
    le prochain changement détectable à l'écran.
  • Produit un rapport JSON + HTML de timing à la fin du replay.
"""

import json
import time
import datetime
import logging
import difflib
import threading
from pathlib import Path
from typing import Optional, Callable

import pyautogui
import easyocr
import numpy as np
from PIL import Image

# Importe les utilitaires multi-moniteurs et label depuis recorder
from recorder import screenshot_region, derive_label

# ─── Configuration ────────────────────────────────────────────────────────────

SESSIONS_DIR   = Path("sessions")
REPORTS_DIR    = Path("reports")
REPORTS_DIR.mkdir(exist_ok=True)

OCR_LANGUAGES         = ["fr", "en"]
OCR_SIMILARITY_MIN    = 0.40    # score minimum pour valider la zone (0–1)
RESPONSE_WAIT_MAX     = 10.0    # secondes max pour détecter un changement écran
RESPONSE_POLL_INTERVAL= 0.05   # intervalle de polling pour la détection (s)
SCREEN_DIFF_THRESHOLD = 0.005   # fraction minimale de pixels modifiés (0–1)
SCREENSHOT_PADDING    = 80      # même valeur que dans recorder.py
ACTION_DELAY_MIN      = 0.05    # délai minimum entre actions (s)
PYAUTOGUI_PAUSE       = 0.1     # pause PyAutoGUI entre commandes (s)

pyautogui.PAUSE        = PYAUTOGUI_PAUSE
pyautogui.FAILSAFE     = True   # coin haut-gauche stoppe le script

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [REPLAYER] %(levelname)s — %(message)s"
)
log = logging.getLogger("replayer")

# ─── Résultat par action ──────────────────────────────────────────────────────

class ActionResult:
    def __init__(self, index: int, action_type: str, timestamp: float,
                 label: str = ""):
        self.index         = index
        self.action_type   = action_type
        self.timestamp     = timestamp
        self.label         = label       # v2 : nom humain de la cible
        self.ocr_match     = None        # float | None
        self.visual_ok     = None        # bool
        self.skipped       = False
        self.error         = None        # str | None
        self.t_action_sent = None        # epoch après exécution de l'action
        self.t_screen_changed = None     # epoch détection changement écran
        self.response_time = None        # float (s)

    def to_dict(self) -> dict:
        return {
            "index":           self.index,
            "action_type":     self.action_type,
            "timestamp":       self.timestamp,
            "label":           self.label,
            "ocr_match_score": round(self.ocr_match, 3) if self.ocr_match is not None else None,
            "visual_ok":       self.visual_ok,
            "skipped":         self.skipped,
            "error":           self.error,
            "t_action_sent":   self.t_action_sent,
            "t_screen_changed":self.t_screen_changed,
            "response_time_s": round(self.response_time, 3) if self.response_time is not None else None,
        }


# ─── Replayer principal ───────────────────────────────────────────────────────

class ActionReplayer:
    def __init__(
        self,
        ocr_similarity_min: float = OCR_SIMILARITY_MIN,
        on_progress: Optional[Callable[[int, int, ActionResult], None]] = None,
    ):
        self.ocr_similarity_min = ocr_similarity_min
        self.on_progress = on_progress
        self._results: list[ActionResult] = []
        self._stop_event = threading.Event()

        log.info("Initialisation EasyOCR…")
        self._reader = easyocr.Reader(OCR_LANGUAGES, gpu=False, verbose=False)
        log.info("EasyOCR prêt.")

    # ── API publique ──────────────────────────────────────────────────────────

    def load_session(self, path: Path) -> dict:
        with open(path, encoding="utf-8") as f:
            return json.load(f)

    def replay(self, session: dict) -> list[ActionResult]:
        """Rejoue toutes les actions de la session. Retourne la liste des résultats."""
        self._results = []
        self._stop_event.clear()
        actions = session.get("actions", [])
        total   = len(actions)

        log.info("Début du replay : %d action(s)", total)

        for i, raw in enumerate(actions):
            if self._stop_event.is_set():
                log.info("Replay interrompu à l'action %d.", i)
                break

            result = self._replay_action(raw, i, total)
            self._results.append(result)

            if self.on_progress:
                self.on_progress(i + 1, total, result)

        log.info("Replay terminé. %d action(s) traitée(s).", len(self._results))
        return self._results

    def stop(self):
        """Arrêt anticipé (appelable depuis un thread UI)."""
        self._stop_event.set()

    def save_report(self, session_path: Path) -> Path:
        """Sauvegarde le rapport JSON et génère le rapport HTML."""
        ts   = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        stem = session_path.stem

        total     = len(self._results)
        ok_count  = sum(1 for r in self._results if not r.skipped and not r.error)
        skip_count= sum(1 for r in self._results if r.skipped)
        err_count = sum(1 for r in self._results if r.error)

        resp_times = [r.response_time for r in self._results if r.response_time is not None]
        avg_resp   = round(sum(resp_times) / len(resp_times), 3) if resp_times else None
        max_resp   = round(max(resp_times), 3) if resp_times else None

        summary = {
            "total":     total,
            "ok":        ok_count,
            "skipped":   skip_count,
            "errors":    err_count,
            "avg_response_time_s": avg_resp,
            "max_response_time_s": max_resp,
        }

        report = {
            "session_file":  str(session_path),
            "replayed_at":   ts,
            "summary": summary,
            "actions": [r.to_dict() for r in self._results],
        }

        # ── JSON ──────────────────────────────────────────────────────────────
        json_path = REPORTS_DIR / f"report_{stem}_{ts}.json"
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        log.info("Rapport JSON sauvegardé → %s", json_path)

        # ── HTML ──────────────────────────────────────────────────────────────
        html_path = REPORTS_DIR / f"report_{stem}_{ts}.html"
        html_content = self._build_html_report(report, stem, ts)
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(html_content)
        log.info("Rapport HTML sauvegardé → %s", html_path)

        return json_path  # compatibilité v1 : retourne le JSON

    def save_report_html(self, session_path: Path) -> Path:
        """Alias pour obtenir uniquement le rapport HTML (retourne son chemin)."""
        ts   = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        stem = session_path.stem
        html_path = REPORTS_DIR / f"report_{stem}_{ts}.html"

        total     = len(self._results)
        ok_count  = sum(1 for r in self._results if not r.skipped and not r.error)
        skip_count= sum(1 for r in self._results if r.skipped)
        err_count = sum(1 for r in self._results if r.error)
        resp_times = [r.response_time for r in self._results if r.response_time is not None]
        avg_resp   = round(sum(resp_times) / len(resp_times), 3) if resp_times else None
        max_resp   = round(max(resp_times), 3) if resp_times else None

        report = {
            "session_file": str(session_path),
            "replayed_at": ts,
            "summary": {
                "total": total, "ok": ok_count,
                "skipped": skip_count, "errors": err_count,
                "avg_response_time_s": avg_resp,
                "max_response_time_s": max_resp,
            },
            "actions": [r.to_dict() for r in self._results],
        }

        html_content = self._build_html_report(report, stem, ts)
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(html_content)
        return html_path

    # ── Génération rapport HTML ───────────────────────────────────────────────

    def _build_html_report(self, report: dict, stem: str, ts: str) -> str:
        """Génère un rapport HTML standalone avec graphique SVG des temps de réponse."""
        summary = report["summary"]
        actions = report["actions"]

        # Données pour le graphique
        chart_data = [
            {
                "index": r["index"],
                "label": r.get("label") or r["action_type"],
                "time":  r.get("response_time_s"),
                "ok":    not r.get("skipped") and not r.get("error"),
                "skip":  r.get("skipped", False),
                "error": bool(r.get("error")),
            }
            for r in actions
        ]

        # Sérialisation JSON pour le JS inline
        chart_json = json.dumps(chart_data, ensure_ascii=False)

        # Tableau HTML des actions
        rows_html = ""
        for r in actions:
            status = "OK" if not r.get("skipped") and not r.get("error") \
                     else ("IGNORÉ" if r.get("skipped") else "ERREUR")
            cls = "ok" if status == "OK" else ("warn" if status == "IGNORÉ" else "err")
            resp = f"{r['response_time_s']:.3f}" if r.get("response_time_s") is not None else "—"
            ocr  = f"{r['ocr_match_score']:.2f}" if r.get("ocr_match_score") is not None else "—"
            label = r.get("label") or "—"
            err_detail = r.get("error") or ""
            rows_html += (
                f'<tr class="{cls}">'
                f'<td>{r["index"]}</td>'
                f'<td>{r["action_type"]}</td>'
                f'<td class="label-cell" title="{err_detail}">{label}</td>'
                f'<td>{ocr}</td>'
                f'<td>{"✔" if r.get("visual_ok") else ("✘" if r.get("visual_ok") is False else "—")}</td>'
                f'<td>{resp}</td>'
                f'<td class="status">{status}</td>'
                f'</tr>\n'
            )

        avg_s = f"{summary['avg_response_time_s']:.3f}s" if summary.get("avg_response_time_s") else "—"
        max_s = f"{summary['max_response_time_s']:.3f}s" if summary.get("max_response_time_s") else "—"
        title = f"WinGhost RPA — Rapport {stem}"
        replayed_at = ts[:4]+"-"+ts[4:6]+"-"+ts[6:8]+" "+ts[9:11]+":"+ts[11:13]+":"+ts[13:]

        return f"""<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>
<style>
  :root {{
    --bg: #1C1F26; --bg2: #252932; --bg3: #2E3440;
    --accent: #5E9BF0; --accent2: #F0965E;
    --green: #4EC9A0; --red: #E06C75; --yellow: #E5C07B;
    --fg: #D8DEE9; --fg2: #7B8496;
    --font: 'Segoe UI', system-ui, sans-serif;
    --mono: Consolas, monospace;
  }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ background: var(--bg); color: var(--fg); font-family: var(--font);
          font-size: 14px; padding: 24px; }}
  h1 {{ font-size: 20px; color: var(--accent); margin-bottom: 4px; }}
  .subtitle {{ color: var(--fg2); font-size: 12px; margin-bottom: 24px; }}
  .cards {{ display: flex; gap: 12px; flex-wrap: wrap; margin-bottom: 28px; }}
  .card {{ background: var(--bg2); border-radius: 8px; padding: 16px 22px;
           min-width: 130px; }}
  .card .val {{ font-size: 28px; font-weight: 700; }}
  .card .lbl {{ font-size: 11px; color: var(--fg2); margin-top: 2px; }}
  .card.ok .val {{ color: var(--green); }}
  .card.warn .val {{ color: var(--yellow); }}
  .card.err .val {{ color: var(--red); }}
  .card.blue .val {{ color: var(--accent); }}

  /* Graphique */
  .chart-wrap {{ background: var(--bg2); border-radius: 8px; padding: 20px;
                 margin-bottom: 28px; overflow-x: auto; }}
  .chart-title {{ font-size: 13px; color: var(--accent); margin-bottom: 12px;
                  font-weight: 600; }}
  #chart-svg {{ display: block; }}

  /* Tableau */
  .table-wrap {{ background: var(--bg2); border-radius: 8px; padding: 16px;
                 overflow-x: auto; }}
  table {{ border-collapse: collapse; width: 100%; font-size: 12px;
           font-family: var(--mono); }}
  th {{ background: var(--bg3); color: var(--accent); font-weight: 600;
        padding: 8px 10px; text-align: left; position: sticky; top: 0; }}
  td {{ padding: 6px 10px; border-bottom: 1px solid var(--bg3); }}
  tr:hover td {{ background: var(--bg3); }}
  tr.ok td {{ color: var(--fg); }}
  tr.warn td {{ color: var(--yellow); }}
  tr.err td {{ color: var(--red); }}
  td.label-cell {{ color: var(--accent2); max-width: 220px;
                   overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
  td.status {{ font-weight: 700; }}

  .footer {{ margin-top: 20px; font-size: 11px; color: var(--fg2); text-align: right; }}
</style>
</head>
<body>

<h1>🤖 WinGhost RPA — Rapport de replay</h1>
<div class="subtitle">Session : {stem} &nbsp;|&nbsp; Rejoué le {replayed_at}</div>

<div class="cards">
  <div class="card blue"><div class="val">{summary["total"]}</div><div class="lbl">Actions total</div></div>
  <div class="card ok"><div class="val">{summary["ok"]}</div><div class="lbl">✔ OK</div></div>
  <div class="card warn"><div class="val">{summary["skipped"]}</div><div class="lbl">⚠ Ignorées</div></div>
  <div class="card err"><div class="val">{summary["errors"]}</div><div class="lbl">✘ Erreurs</div></div>
  <div class="card blue"><div class="val">{avg_s}</div><div class="lbl">⏱ Moy. réponse</div></div>
  <div class="card warn"><div class="val">{max_s}</div><div class="lbl">⏱ Max réponse</div></div>
</div>

<div class="chart-wrap">
  <div class="chart-title">Temps de réponse applicatif par action (secondes)</div>
  <svg id="chart-svg" xmlns="http://www.w3.org/2000/svg"></svg>
</div>

<div class="table-wrap">
  <table>
    <thead><tr>
      <th>#</th><th>Type</th><th>Cible</th>
      <th>Score OCR</th><th>Visuel OK</th><th>Réponse (s)</th><th>Statut</th>
    </tr></thead>
    <tbody>
{rows_html}    </tbody>
  </table>
</div>

<div class="footer">Généré par WinGhost RPA v2 — {replayed_at}</div>

<script>
(function() {{
  const data = {chart_json};

  const hasTime = data.filter(d => d.time != null);
  if (hasTime.length === 0) {{
    document.querySelector('.chart-wrap').style.display = 'none';
    return;
  }}

  const maxTime = Math.max(...hasTime.map(d => d.time), 1.0);
  const BAR_W = 28, GAP = 6, PAD_L = 48, PAD_R = 20, PAD_T = 16, PAD_B = 60;
  const CHART_H = 220;
  const totalW = PAD_L + data.length * (BAR_W + GAP) + PAD_R;
  const svgH = PAD_T + CHART_H + PAD_B;

  const svg = document.getElementById('chart-svg');
  svg.setAttribute('viewBox', `0 0 ${{totalW}} ${{svgH}}`);
  svg.setAttribute('width', Math.max(totalW, 600));
  svg.setAttribute('height', svgH);

  const ns = 'http://www.w3.org/2000/svg';
  const mk = (tag, attrs) => {{
    const el = document.createElementNS(ns, tag);
    for (const [k,v] of Object.entries(attrs)) el.setAttribute(k, v);
    return el;
  }};

  // Grid lines
  [0, 0.25, 0.5, 0.75, 1.0].forEach(frac => {{
    const y = PAD_T + CHART_H - frac * CHART_H;
    const val = (frac * maxTime).toFixed(2);
    svg.appendChild(mk('line', {{
      x1: PAD_L - 4, y1: y, x2: totalW - PAD_R, y2: y,
      stroke: '#2E3440', 'stroke-width': 1
    }}));
    const lbl = mk('text', {{
      x: PAD_L - 6, y: y + 4,
      fill: '#7B8496', 'font-size': 10, 'text-anchor': 'end',
      'font-family': 'Consolas, monospace'
    }});
    lbl.textContent = val + 's';
    svg.appendChild(lbl);
  }});

  // Axe Y
  svg.appendChild(mk('line', {{
    x1: PAD_L, y1: PAD_T, x2: PAD_L, y2: PAD_T + CHART_H,
    stroke: '#3E4450', 'stroke-width': 1
  }}));

  // Barres
  data.forEach((d, i) => {{
    const bx = PAD_L + i * (BAR_W + GAP);
    if (d.time != null) {{
      const bh = (d.time / maxTime) * CHART_H;
      const by = PAD_T + CHART_H - bh;
      const color = d.error ? '#E06C75' : (d.skip ? '#E5C07B' : '#5E9BF0');
      const bar = mk('rect', {{
        x: bx, y: by, width: BAR_W, height: bh,
        fill: color, rx: 3
      }});
      // Tooltip title
      const title = document.createElementNS(ns, 'title');
      title.textContent = `#${{d.index}} ${{d.label}}\\n${{d.time.toFixed(3)}}s`;
      bar.appendChild(title);
      svg.appendChild(bar);

      // Valeur au-dessus
      const vt = mk('text', {{
        x: bx + BAR_W/2, y: by - 3,
        fill: '#D8DEE9', 'font-size': 9, 'text-anchor': 'middle',
        'font-family': 'Consolas, monospace'
      }});
      vt.textContent = d.time.toFixed(2);
      svg.appendChild(vt);
    }} else {{
      // Marqueur "—" pour actions sans temps
      const dash = mk('rect', {{
        x: bx, y: PAD_T + CHART_H - 4, width: BAR_W, height: 4,
        fill: '#3E4450', rx: 2
      }});
      svg.appendChild(dash);
    }}

    // Label axe X (tronqué)
    const lbl_txt = (d.label || d.action_type).substring(0, 8);
    const xl = mk('text', {{
      x: bx + BAR_W/2, y: PAD_T + CHART_H + 14,
      fill: '#7B8496', 'font-size': 9, 'text-anchor': 'middle',
      'font-family': 'Consolas, monospace'
    }});
    xl.textContent = lbl_txt;
    svg.appendChild(xl);

    const xi = mk('text', {{
      x: bx + BAR_W/2, y: PAD_T + CHART_H + 26,
      fill: '#3E4450', 'font-size': 8, 'text-anchor': 'middle',
      'font-family': 'Consolas, monospace'
    }});
    xi.textContent = '#' + d.index;
    svg.appendChild(xi);
  }});

  // Ligne moyenne
  const avgT = hasTime.reduce((s, d) => s + d.time, 0) / hasTime.length;
  const avgY = PAD_T + CHART_H - (avgT / maxTime) * CHART_H;
  svg.appendChild(mk('line', {{
    x1: PAD_L, y1: avgY, x2: totalW - PAD_R, y2: avgY,
    stroke: '#F0965E', 'stroke-width': 1.5, 'stroke-dasharray': '6 3'
  }}));
  const avgLbl = mk('text', {{
    x: totalW - PAD_R - 2, y: avgY - 4,
    fill: '#F0965E', 'font-size': 9, 'text-anchor': 'end',
    'font-family': 'Consolas, monospace'
  }});
  avgLbl.textContent = 'moy ' + avgT.toFixed(2) + 's';
  svg.appendChild(avgLbl);
}})();
</script>
</body>
</html>"""

    # ── Exécution d'une action ─────────────────────────────────────────────────

    def _replay_action(self, raw: dict, i: int, total: int) -> ActionResult:
        # Récupère le label enregistré dans la session (v2) ou le déduit
        visual_ctx = raw.get("visual_context")
        if visual_ctx and visual_ctx.get("label"):
            label = visual_ctx["label"]
        elif visual_ctx and visual_ctx.get("ocr_text"):
            label = derive_label(visual_ctx["ocr_text"], raw.get("action_type", "click"))
        else:
            label = raw.get("action_type", "")

        result = ActionResult(
            index       = raw.get("index", i + 1),
            action_type = raw.get("action_type", "unknown"),
            timestamp   = raw.get("timestamp", 0),
            label       = label,
        )

        # ── Délai inter-actions ──────────────────────────────────────────────
        delay = max(raw.get("delay_before", 0), ACTION_DELAY_MIN)
        time.sleep(delay)

        # ── Vérification visuelle ────────────────────────────────────────────
        if visual_ctx and visual_ctx.get("ocr_text"):
            ok, score = self._verify_visual(
                raw.get("x"), raw.get("y"),
                visual_ctx["screenshot_region"],
                visual_ctx["ocr_text"],
            )
            result.ocr_match = score
            result.visual_ok = ok
            if not ok:
                result.skipped = True
                result.error   = (
                    f"Contexte visuel non reconnu "
                    f"(score={score:.2f} < seuil={self.ocr_similarity_min:.2f}) — "
                    f"cible: {label!r}"
                )
                log.warning("[%d/%d] Action %d IGNORÉE — cible: %r score=%.2f",
                            i+1, total, result.index, label, score)
                return result
        else:
            result.visual_ok = None

        # ── Capture pré-action (référence pour mesure de réponse) ────────────
        pre_screenshot = self._take_full_screenshot()

        # ── Exécution ────────────────────────────────────────────────────────
        try:
            self._execute(raw)
            result.t_action_sent = time.time()
        except Exception as e:
            result.error = f"Erreur exécution : {e}"
            log.error("[%d/%d] Action %d ERREUR : %s",
                      i+1, total, result.index, e)
            return result

        log.info("[%d/%d] Action %d (%s) — cible: %r — exécutée.",
                 i+1, total, result.index, result.action_type, label)

        # ── Mesure du temps de réponse applicatif ────────────────────────────
        changed_at = self._wait_for_screen_change(pre_screenshot)
        result.t_screen_changed = changed_at
        if changed_at is not None:
            result.response_time = round(changed_at - result.t_action_sent, 3)
            log.info("    ↳ Temps de réponse : %.3f s", result.response_time)
        else:
            log.info("    ↳ Aucun changement écran détecté dans %.1f s",
                     RESPONSE_WAIT_MAX)

        return result

    # ── Vérification OCR ──────────────────────────────────────────────────────

    def _verify_visual(
        self,
        x: Optional[int], y: Optional[int],
        region: list,
        expected_text: str,
    ) -> tuple[bool, float]:
        try:
            rx, ry, rw, rh = region
            # Utilise screenshot_region multi-moniteur si x,y disponibles
            if x is not None and y is not None:
                img, _ = screenshot_region(x, y, SCREENSHOT_PADDING)
            else:
                img = pyautogui.screenshot(region=(rx, ry, rw, rh))
            img_np     = np.array(img)
            results    = self._reader.readtext(img_np, detail=0)
            current_text = " | ".join(results).strip()

            score = difflib.SequenceMatcher(
                None,
                expected_text.lower(),
                current_text.lower(),
            ).ratio()

            log.debug("OCR attendu : %r", expected_text[:60])
            log.debug("OCR actuel  : %r — score=%.2f", current_text[:60], score)

            return score >= self.ocr_similarity_min, score

        except Exception as e:
            log.warning("Erreur vérification visuelle : %s", e)
            return False, 0.0

    # ── Exécution de l'action ─────────────────────────────────────────────────

    def _execute(self, raw: dict):
        atype = raw.get("action_type")
        x, y  = raw.get("x"), raw.get("y")

        if atype == "click":
            pyautogui.click(x, y)

        elif atype == "double_click":
            pyautogui.doubleClick(x, y)

        elif atype == "right_click":
            pyautogui.rightClick(x, y)

        elif atype == "type":
            if x and y:
                pyautogui.click(x, y)
                time.sleep(0.1)
            text = raw.get("text", "")
            pyautogui.typewrite(text, interval=0.03)

        elif atype == "key":
            key = raw.get("key", "")
            key_map = {
                "enter":   "enter", "tab":     "tab",
                "escape":  "esc",   "space":   "space",
                "backspace": "backspace", "delete":  "delete",
                "up": "up", "down": "down", "left": "left", "right": "right",
                "home": "home", "end": "end",
                "page_up": "pageup", "page_down": "pagedown",
                "f1": "f1", "f2": "f2", "f3": "f3", "f4": "f4",
                "f5": "f5", "f6": "f6", "f7": "f7", "f8": "f8",
            }
            pyautogui.press(key_map.get(key, key))

        else:
            raise ValueError(f"Type d'action inconnu : {atype!r}")

    # ── Détection de changement d'écran (tous moniteurs) ─────────────────────

    def _take_full_screenshot(self) -> np.ndarray:
        """Capture l'ensemble du bureau (tous moniteurs fusionnés par pyautogui)."""
        return np.array(pyautogui.screenshot())

    def _wait_for_screen_change(
        self,
        reference: np.ndarray,
    ) -> Optional[float]:
        deadline = time.time() + RESPONSE_WAIT_MAX
        ref_gray = np.mean(reference, axis=2).astype(np.float32)

        while time.time() < deadline:
            if self._stop_event.is_set():
                return None
            time.sleep(RESPONSE_POLL_INTERVAL)

            current      = self._take_full_screenshot()
            current_gray = np.mean(current, axis=2).astype(np.float32)

            # Recadre si résolution différente (changement moniteur)
            h = min(ref_gray.shape[0], current_gray.shape[0])
            w = min(ref_gray.shape[1], current_gray.shape[1])
            diff         = np.abs(current_gray[:h, :w] - ref_gray[:h, :w])
            changed_frac = np.mean(diff > 10)

            if changed_frac >= SCREEN_DIFF_THRESHOLD:
                return time.time()

        return None


# ─── CLI simple ───────────────────────────────────────────────────────────────

def main():
    import sys

    if len(sys.argv) < 2:
        sessions = sorted(SESSIONS_DIR.glob("session_*.json"))
        if not sessions:
            print("Aucune session trouvée dans", SESSIONS_DIR)
            sys.exit(1)
        session_path = sessions[-1]
        print(f"Dernière session : {session_path}")
    else:
        session_path = Path(sys.argv[1])

    replayer = ActionReplayer()
    session  = replayer.load_session(session_path)
    results  = replayer.replay(session)
    json_path = replayer.save_report(session_path)
    html_path = str(json_path).replace(".json", ".html")

    print(f"\nRapport JSON → {json_path}")
    print(f"Rapport HTML → {html_path}")
    print(f"Actions : {len(results)} | "
          f"OK : {sum(1 for r in results if not r.skipped and not r.error)} | "
          f"Ignorées : {sum(1 for r in results if r.skipped)} | "
          f"Erreurs : {sum(1 for r in results if r.error)}")


if __name__ == "__main__":
    main()
