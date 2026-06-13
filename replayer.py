"""
replayer.py — Replay de session avec vérification OCR optionnelle et mesure de timing.

v6.3 : le gate visuel OCR (« ne rejouer que si le contexte visuel correspond »)
       devient OPTIONNEL et DÉSACTIVÉ par défaut (`visual_gate=False`).
       Par défaut, toutes les actions sont rejouées sans contrôle OCR.

v6.1 : rejeu de TOUS les inputs souris — clic milieu (middle_click), molette
       (scroll), glisser-déposer (drag) ; seuil OCR par défaut abaissé à 0.25

v6 : gestion de l'action "move" (déplacement souris throttlé depuis le recorder)
     + paramètre `reader` pour réutiliser un lecteur OCR partagé

v5 :
  • app_response_ms : temps applicatif cumulé (somme des temps de réponse)
    persisté en plus de total_duration_s (temps de bout en bout horloge)
  • write_official_log() : priorité au champ target_app du scénario pour app_name

v4 :
  • Screenshots TOUJOURS capturés (paramètre capture_screenshots supprimé)
  • SCREENSHOT_REGION_PAD = 160 px (était 120)
  • write_official_log() : écrit dans le journal officiel CSV après chaque run
  • save_to_db() appelle automatiquement write_official_log()
  • _last_session : dernier dict de session chargé (pour scenario_name)
  • SCENARIOS_DIR listé en plus de SESSIONS_DIR pour les fichiers scénario

v3 (conservé) :
  • MultiReplayRunner : N runs consécutifs d'une même session, avec intervalle configurable
  • Persistance des résultats dans SQLite via stats_db
  • ActionResult enrichi : screenshot_b64, response_time_ms (en ms en plus de s)
  • save_report() génère JSON + HTML + persiste en DB en une passe
  • Rétrocompatible avec les sessions v1 et v2

v2 (conservé) :
  • ActionResult.label, vérification OCR, temps de réponse applicatif
  • Rapport HTML standalone avec graphique SVG
  • Support multi-moniteurs
"""

import base64
import collections
import datetime
import difflib
import io
import json
import logging
import threading
import time
from pathlib import Path
from typing import Callable, Optional

import numpy as np
import pyautogui
import easyocr
from PIL import Image

from recorder import screenshot_region, derive_label
import stats_db
import official_log

# ─── Configuration ────────────────────────────────────────────────────────────

SESSIONS_DIR           = Path("sessions")
SCENARIOS_DIR          = Path("scenarios")
REPORTS_DIR            = Path("reports")
REPORTS_DIR.mkdir(exist_ok=True)

OCR_LANGUAGES          = ["fr", "en"]
OCR_SIMILARITY_MIN     = 0.25   # v6.1 : abaissé (était 0.40) pour réduire les
                                #        faux négatifs qui faisaient sauter les clics
SCROLL_REPLAY_AMOUNT   = 100    # facteur appliqué à dy/dx de la molette au rejeu
RESPONSE_WAIT_MAX      = 10.0
RESPONSE_POLL_INTERVAL = 0.05
SCREEN_DIFF_THRESHOLD  = 0.005
SCREENSHOT_PADDING     = 80
ACTION_DELAY_MIN       = 0.05
PYAUTOGUI_PAUSE        = 0.1
SCREENSHOT_REGION_PAD  = 160   # padding plus large pour le screenshot post-action

pyautogui.PAUSE    = PYAUTOGUI_PAUSE
pyautogui.FAILSAFE = True

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [REPLAYER] %(levelname)s — %(message)s",
)
log = logging.getLogger("replayer")


# ─── Résultat par action ──────────────────────────────────────────────────────

class ActionResult:
    def __init__(self, index: int, action_type: str, timestamp: float,
                 label: str = "", x: Optional[int] = None, y: Optional[int] = None,
                 app_name: str = ""):
        self.index            = index
        self.action_type      = action_type
        self.timestamp        = timestamp
        self.label            = label
        self.x                = x
        self.y                = y
        self.app_name         = app_name
        self.ocr_match        = None   # float | None
        self.visual_ok        = None   # bool | None
        self.skipped          = False
        self.error            = None   # str | None
        self.t_action_sent    = None   # epoch
        self.t_screen_changed = None   # epoch
        self.response_time    = None   # float (s)
        self.screenshot_b64   = None   # str | None  (PNG base64)

    @property
    def response_time_ms(self) -> Optional[float]:
        return round(self.response_time * 1000, 1) if self.response_time is not None else None

    @property
    def status(self) -> str:
        if self.skipped:
            return "skip"
        if self.error:
            return "error"
        return "ok"

    def to_dict(self) -> dict:
        return {
            "index":            self.index,
            "action_type":      self.action_type,
            "timestamp":        self.timestamp,
            "label":            self.label,
            "x":                self.x,
            "y":                self.y,
            "app_name":         self.app_name,
            "ocr_match_score":  round(self.ocr_match, 3) if self.ocr_match is not None else None,
            "visual_ok":        self.visual_ok,
            "skipped":          self.skipped,
            "error":            self.error,
            "t_action_sent":    self.t_action_sent,
            "t_screen_changed": self.t_screen_changed,
            "response_time_s":  round(self.response_time, 3) if self.response_time is not None else None,
            "response_time_ms": self.response_time_ms,
            "screenshot_b64":   self.screenshot_b64,
        }


# ─── Replayer principal ───────────────────────────────────────────────────────

class ActionReplayer:
    def __init__(
        self,
        ocr_similarity_min: float = OCR_SIMILARITY_MIN,
        on_progress: Optional[Callable[[int, int, "ActionResult"], None]] = None,
        reader=None,
        visual_gate: bool = False,
    ):
        self.ocr_similarity_min  = ocr_similarity_min
        # v6.3 : gate OCR optionnel, désactivé par défaut. Lorsqu'il est faux,
        # aucune vérification visuelle n'est faite et toutes les actions sont rejouées.
        self.visual_gate         = visual_gate
        self.on_progress         = on_progress
        self._results: list[ActionResult] = []
        self._stop_event = threading.Event()
        self._last_session: dict = {}
        self._reader = reader

        # L'OCR n'est nécessaire que si le gate visuel est actif. On n'initialise
        # EasyOCR (coûteux) que dans ce cas et seulement si aucun lecteur partagé
        # n'a été fourni.
        if not visual_gate:
            log.info("Gate visuel OCR désactivé — rejeu sans vérification.")
        elif reader is not None:
            log.info("Utilisation du lecteur OCR partagé.")
        else:
            log.info("Initialisation EasyOCR…")
            self._reader = easyocr.Reader(OCR_LANGUAGES, gpu=False, verbose=False)
            log.info("EasyOCR prêt.")

    # ── API publique ──────────────────────────────────────────────────────────

    def load_session(self, path: Path) -> dict:
        with open(path, encoding="utf-8") as f:
            session = json.load(f)
        self._last_session = session
        return session

    def replay(self, session: dict) -> list[ActionResult]:
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
        self._stop_event.set()

    def save_report(self, session_path: Path) -> Path:
        """Sauvegarde JSON (sans screenshots) + HTML (avec screenshots inline)."""
        ts   = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        stem = session_path.stem
        report = self._build_report_dict(session_path, ts)

        # JSON sans screenshots pour rester lisible
        json_path = REPORTS_DIR / f"report_{stem}_{ts}.json"
        report_lean = {
            **report,
            "actions": [
                {k: v for k, v in a.items() if k != "screenshot_b64"}
                for a in report["actions"]
            ],
        }
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(report_lean, f, ensure_ascii=False, indent=2)
        log.info("Rapport JSON → %s", json_path)

        # HTML avec screenshots inline
        html_path = REPORTS_DIR / f"report_{stem}_{ts}.html"
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(self._build_html_report(report, stem, ts))
        log.info("Rapport HTML → %s", html_path)

        return json_path

    def write_official_log(self, session_path: Path, scenario_name: str = "") -> None:
        """
        Écrit une entrée dans le journal officiel CSV (official_log.py).

        - Calcule la durée depuis les timestamps t_action_sent du premier/dernier résultat.
        - Détermine le statut : SUCCÈS si tout ok, PARTIEL si seulement des skips, ÉCHEC si erreur.
        - Récupère app_name depuis le résultat le plus fréquent (Counter sur valeurs non vides).
        - Utilise scenario_name fourni en paramètre, ou issu de self._last_session, ou le stem.
        """
        if not self._results:
            return

        # Durée : du premier au dernier t_action_sent (ou timestamp)
        times = [r.t_action_sent for r in self._results if r.t_action_sent is not None]
        if len(times) >= 2:
            duration_s = round(times[-1] - times[0], 3)
        elif len(times) == 1:
            duration_s = 0.0
        else:
            # fallback sur les timestamps enregistrés
            ts_list = [r.timestamp for r in self._results if r.timestamp]
            duration_s = round(ts_list[-1] - ts_list[0], 3) if len(ts_list) >= 2 else 0.0

        # Statut
        has_error = any(r.status == "error" for r in self._results)
        has_skip  = any(r.status == "skip"  for r in self._results)
        if has_error:
            status = official_log.STATUS_FAILURE
        elif has_skip:
            status = official_log.STATUS_PARTIAL
        else:
            status = official_log.STATUS_SUCCESS

        ok_count    = sum(1 for r in self._results if r.status == "ok")
        total_count = len(self._results)

        # app_name : application cible déclarée dans le scénario (prioritaire),
        # sinon valeur la plus fréquente capturée parmi les actions.
        app_name = self._last_session.get("target_app", "") or ""
        if not app_name:
            app_names = [r.app_name for r in self._results if getattr(r, "app_name", "")]
            if app_names:
                counter  = collections.Counter(app_names)
                app_name = counter.most_common(1)[0][0]

        # scenario_name : paramètre > session dict > stem du fichier
        if not scenario_name:
            scenario_name = self._last_session.get("scenario_name", "") or session_path.stem

        # run_id : on obtient le dernier run_id depuis stats_db si disponible
        # (appelé après save_to_db, donc on relit le dernier run de la session)
        run_id = 0
        try:
            stats_db.init_db()
            fp = str(session_path.resolve())
            rows = stats_db.get_all_sessions()
            for s in rows:
                if s.get("filepath") == fp:
                    runs = stats_db.get_session_runs(s["id"])
                    if runs:
                        run_id = runs[-1]["id"]
                    break
        except Exception:
            pass

        execution_date = datetime.datetime.now().isoformat(timespec="seconds")

        try:
            official_log.append_entry(
                app_name       = app_name,
                scenario_name  = scenario_name,
                execution_date = execution_date,
                duration_s     = duration_s,
                status         = status,
                ok_count       = ok_count,
                total_count    = total_count,
                run_id         = run_id,
            )
            log.info("Journal officiel mis à jour (statut=%s, run_id=%d).", status, run_id)
        except Exception as e:
            log.warning("Impossible d'écrire dans le journal officiel : %s", e)

    def save_to_db(self, session_path: Path) -> int:
        """Persiste le dernier replay dans SQLite. Retourne le run_id."""
        stats_db.init_db()

        scenario_name = self._last_session.get("scenario_name", "") or session_path.stem

        session_id = stats_db.upsert_session(
            filepath=str(session_path.resolve()),
            name=session_path.stem,
            action_count=len(self._results),
            scenario_name=scenario_name,
        )
        run_number = stats_db.next_run_number(session_id)
        started_at = datetime.datetime.now().isoformat(timespec="seconds")
        run_id     = stats_db.insert_run(session_id, run_number, started_at)

        times = [r.response_time_ms for r in self._results if r.response_time_ms is not None]
        now   = datetime.datetime.now().isoformat(timespec="seconds")

        # Durée totale (bout en bout, horloge murale) pour finish_run
        t_times = [r.t_action_sent for r in self._results if r.t_action_sent is not None]
        total_duration_s = round(t_times[-1] - t_times[0], 3) if len(t_times) >= 2 else None

        # Temps applicatif cumulé : somme des temps de réponse mesurés
        app_response_ms = round(sum(times), 1) if times else None

        for r in self._results:
            stats_db.insert_action_result(
                run_id=run_id,
                action_index=r.index,
                action_type=r.action_type,
                label=r.label or "",
                x=r.x,
                y=r.y,
                ocr_score=r.ocr_match,
                visual_ok=r.visual_ok,
                response_time_ms=r.response_time_ms,
                status=r.status,
                error_msg=r.error,
                screenshot_b64=r.screenshot_b64,
                replayed_at=now,
                app_name=getattr(r, "app_name", ""),
            )

        stats_db.finish_run(
            run_id=run_id,
            ended_at=datetime.datetime.now().isoformat(timespec="seconds"),
            total=len(self._results),
            ok=sum(1 for r in self._results if r.status == "ok"),
            skip=sum(1 for r in self._results if r.status == "skip"),
            errors=sum(1 for r in self._results if r.status == "error"),
            avg_ms=round(sum(times) / len(times), 1) if times else None,
            max_ms=round(max(times), 1) if times else None,
            total_duration_s=total_duration_s,
            app_response_ms=app_response_ms,
        )
        log.info("Run #%d persisté en DB (session_id=%d, run_id=%d).",
                 run_number, session_id, run_id)

        # Écriture dans le journal officiel
        self.write_official_log(session_path, scenario_name=scenario_name)

        return run_id

    # ── Génération rapport ────────────────────────────────────────────────────

    def _build_report_dict(self, session_path: Path, ts: str) -> dict:
        total      = len(self._results)
        ok_count   = sum(1 for r in self._results if r.status == "ok")
        skip_count = sum(1 for r in self._results if r.status == "skip")
        err_count  = sum(1 for r in self._results if r.status == "error")
        times      = [r.response_time for r in self._results if r.response_time is not None]
        return {
            "session_file": str(session_path),
            "replayed_at":  ts,
            "summary": {
                "total":               total,
                "ok":                  ok_count,
                "skipped":             skip_count,
                "errors":              err_count,
                "avg_response_time_s": round(sum(times) / len(times), 3) if times else None,
                "max_response_time_s": round(max(times), 3) if times else None,
            },
            "actions": [r.to_dict() for r in self._results],
        }

    def _build_html_report(self, report: dict, stem: str, ts: str) -> str:
        summary = report["summary"]
        actions = report["actions"]

        chart_data = [
            {
                "index": r["index"],
                "label": r.get("label") or r["action_type"],
                "time":  r.get("response_time_s"),
                "status": ("skip" if r.get("skipped") else ("error" if r.get("error") else "ok")),
            }
            for r in actions
        ]
        chart_json = json.dumps(chart_data, ensure_ascii=False)

        rows_html = ""
        for r in actions:
            status = "IGNORÉ" if r.get("skipped") else ("ERREUR" if r.get("error") else "OK")
            cls    = {"OK": "ok", "IGNORÉ": "warn", "ERREUR": "err"}[status]
            resp   = f"{r['response_time_s']:.3f}" if r.get("response_time_s") is not None else "—"
            ocr    = f"{r['ocr_match_score']:.2f}" if r.get("ocr_match_score") is not None else "—"
            label  = r.get("label") or "—"
            err_d  = r.get("error") or ""
            ss     = r.get("screenshot_b64") or ""
            ss_cell = (
                f'<td><img class="ss-thumb" src="data:image/png;base64,{ss}" '
                f'title="{label}" alt="screenshot"></td>'
                if ss else "<td>—</td>"
            )
            rows_html += (
                f'<tr class="{cls}">'
                f'<td>{r["index"]}</td><td>{r["action_type"]}</td>'
                f'<td class="label-cell" title="{err_d}">{label}</td>'
                f'<td>{ocr}</td>'
                f'<td>{"✔" if r.get("visual_ok") else ("✘" if r.get("visual_ok") is False else "—")}</td>'
                f'<td>{resp}</td>{ss_cell}'
                f'<td class="status">{status}</td>'
                f'</tr>\n'
            )

        avg_s = f"{summary['avg_response_time_s']:.3f}s" if summary.get("avg_response_time_s") else "—"
        max_s = f"{summary['max_response_time_s']:.3f}s" if summary.get("max_response_time_s") else "—"
        replayed_at = (ts[:4]+"-"+ts[4:6]+"-"+ts[6:8]+" "
                       +ts[9:11]+":"+ts[11:13]+":"+ts[13:])

        return f"""<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>WinGhost RPA — Rapport {stem}</title>
<style>
:root{{--bg:#1C1F26;--bg2:#252932;--bg3:#2E3440;--accent:#5E9BF0;--accent2:#F0965E;
      --green:#4EC9A0;--red:#E06C75;--yellow:#E5C07B;--fg:#D8DEE9;--fg2:#7B8496;
      --font:'Segoe UI',system-ui,sans-serif;--mono:Consolas,monospace}}
*{{box-sizing:border-box;margin:0;padding:0}}
body{{background:var(--bg);color:var(--fg);font-family:var(--font);font-size:14px;padding:24px}}
h1{{font-size:20px;color:var(--accent);margin-bottom:4px}}
.subtitle{{color:var(--fg2);font-size:12px;margin-bottom:24px}}
.cards{{display:flex;gap:12px;flex-wrap:wrap;margin-bottom:28px}}
.card{{background:var(--bg2);border-radius:8px;padding:16px 22px;min-width:130px}}
.card .val{{font-size:28px;font-weight:700}}.card .lbl{{font-size:11px;color:var(--fg2);margin-top:2px}}
.card.ok .val{{color:var(--green)}}.card.warn .val{{color:var(--yellow)}}
.card.err .val{{color:var(--red)}}.card.blue .val{{color:var(--accent)}}
.chart-wrap{{background:var(--bg2);border-radius:8px;padding:20px;margin-bottom:28px;overflow-x:auto}}
.chart-title{{font-size:13px;color:var(--accent);margin-bottom:12px;font-weight:600}}
.table-wrap{{background:var(--bg2);border-radius:8px;padding:16px;overflow-x:auto}}
table{{border-collapse:collapse;width:100%;font-size:12px;font-family:var(--mono)}}
th{{background:var(--bg3);color:var(--accent);font-weight:600;padding:8px 10px;
    text-align:left;position:sticky;top:0}}
td{{padding:6px 10px;border-bottom:1px solid var(--bg3)}}
tr:hover td{{background:var(--bg3)}}
tr.ok td{{color:var(--fg)}}tr.warn td{{color:var(--yellow)}}tr.err td{{color:var(--red)}}
td.label-cell{{color:var(--accent2);max-width:200px;overflow:hidden;
               text-overflow:ellipsis;white-space:nowrap}}
td.status{{font-weight:700}}
.ss-thumb{{height:48px;width:auto;border-radius:4px;cursor:zoom-in;
           transition:transform .15s;border:1px solid var(--bg3)}}
.ss-thumb:hover{{transform:scale(3.5);z-index:10;position:relative}}
.footer{{margin-top:20px;font-size:11px;color:var(--fg2);text-align:right}}
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
      <th>Score OCR</th><th>Visuel OK</th><th>Réponse (s)</th>
      <th>Screenshot</th><th>Statut</th>
    </tr></thead>
    <tbody>{rows_html}</tbody>
  </table>
</div>
<div class="footer">Généré par WinGhost RPA v4 — {replayed_at}</div>
<script>
(function(){{
  const data={chart_json};
  const hasTime=data.filter(d=>d.time!=null);
  if(!hasTime.length){{document.querySelector('.chart-wrap').style.display='none';return;}}
  const maxTime=Math.max(...hasTime.map(d=>d.time),1.0);
  const BAR_W=28,GAP=6,PAD_L=48,PAD_R=20,PAD_T=16,PAD_B=60,CHART_H=220;
  const totalW=PAD_L+data.length*(BAR_W+GAP)+PAD_R,svgH=PAD_T+CHART_H+PAD_B;
  const svg=document.getElementById('chart-svg');
  svg.setAttribute('viewBox',`0 0 ${{totalW}} ${{svgH}}`);
  svg.setAttribute('width',Math.max(totalW,600));svg.setAttribute('height',svgH);
  const ns='http://www.w3.org/2000/svg';
  const mk=(tag,a)=>{{const el=document.createElementNS(ns,tag);
    for(const[k,v]of Object.entries(a))el.setAttribute(k,v);return el;}};
  [0,.25,.5,.75,1].forEach(frac=>{{
    const y=PAD_T+CHART_H-frac*CHART_H;
    svg.appendChild(mk('line',{{x1:PAD_L-4,y1:y,x2:totalW-PAD_R,y2:y,stroke:'#2E3440','stroke-width':1}}));
    const t=mk('text',{{x:PAD_L-6,y:y+4,fill:'#7B8496','font-size':10,'text-anchor':'end',
      'font-family':'Consolas,monospace'}});t.textContent=(frac*maxTime).toFixed(2)+'s';svg.appendChild(t);
  }});
  svg.appendChild(mk('line',{{x1:PAD_L,y1:PAD_T,x2:PAD_L,y2:PAD_T+CHART_H,stroke:'#3E4450','stroke-width':1}}));
  data.forEach((d,i)=>{{
    const bx=PAD_L+i*(BAR_W+GAP);
    if(d.time!=null){{
      const bh=(d.time/maxTime)*CHART_H,by=PAD_T+CHART_H-bh;
      const color=d.status==='error'?'#E06C75':(d.status==='skip'?'#E5C07B':'#5E9BF0');
      const bar=mk('rect',{{x:bx,y:by,width:BAR_W,height:bh,fill:color,rx:3}});
      const tt=document.createElementNS(ns,'title');
      tt.textContent=`#${{d.index}} ${{d.label}}\\n${{d.time.toFixed(3)}}s`;
      bar.appendChild(tt);svg.appendChild(bar);
      const vt=mk('text',{{x:bx+BAR_W/2,y:by-3,fill:'#D8DEE9','font-size':9,
        'text-anchor':'middle','font-family':'Consolas,monospace'}});
      vt.textContent=d.time.toFixed(2);svg.appendChild(vt);
    }}else{{
      svg.appendChild(mk('rect',{{x:bx,y:PAD_T+CHART_H-4,width:BAR_W,height:4,fill:'#3E4450',rx:2}}));
    }}
    const xl=mk('text',{{x:bx+BAR_W/2,y:PAD_T+CHART_H+14,fill:'#7B8496','font-size':9,
      'text-anchor':'middle','font-family':'Consolas,monospace'}});
    xl.textContent=(d.label||d.action_type).substring(0,8);svg.appendChild(xl);
    const xi=mk('text',{{x:bx+BAR_W/2,y:PAD_T+CHART_H+26,fill:'#3E4450','font-size':8,
      'text-anchor':'middle','font-family':'Consolas,monospace'}});
    xi.textContent='#'+d.index;svg.appendChild(xi);
  }});
  const avgT=hasTime.reduce((s,d)=>s+d.time,0)/hasTime.length;
  const avgY=PAD_T+CHART_H-(avgT/maxTime)*CHART_H;
  svg.appendChild(mk('line',{{x1:PAD_L,y1:avgY,x2:totalW-PAD_R,y2:avgY,
    stroke:'#F0965E','stroke-width':1.5,'stroke-dasharray':'6 3'}}));
  const al=mk('text',{{x:totalW-PAD_R-2,y:avgY-4,fill:'#F0965E','font-size':9,
    'text-anchor':'end','font-family':'Consolas,monospace'}});
  al.textContent='moy '+avgT.toFixed(2)+'s';svg.appendChild(al);
}})();
</script>
</body>
</html>"""

    # ── Exécution d'une action ─────────────────────────────────────────────────

    def _replay_action(self, raw: dict, i: int, total: int) -> ActionResult:
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
            x           = raw.get("x"),
            y           = raw.get("y"),
            app_name    = raw.get("app_name", ""),
        )

        delay = max(raw.get("delay_before", 0), ACTION_DELAY_MIN)
        time.sleep(delay)

        # Mouvements souris : exécution directe, pas de vérification OCR
        if raw.get("action_type") == "move":
            if raw.get("x") is not None and raw.get("y") is not None:
                try:
                    pyautogui.moveTo(raw["x"], raw["y"], duration=max(delay * 0.4, 0.02))
                except Exception:
                    pass
            result.t_action_sent = time.time()
            return result

        # Vérification visuelle OCR — uniquement si le gate visuel est activé (v6.3).
        # Par défaut (gate désactivé), aucune vérification : l'action est toujours rejouée.
        if self.visual_gate and visual_ctx and visual_ctx.get("ocr_text"):
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
                log.warning("[%d/%d] #%d IGNORÉE — %r score=%.2f",
                            i+1, total, result.index, label, score)
                return result
        else:
            result.visual_ok = None

        pre_screenshot = self._take_full_screenshot()

        try:
            self._execute(raw)
            result.t_action_sent = time.time()
        except Exception as e:
            result.error = f"Erreur exécution : {e}"
            log.error("[%d/%d] #%d ERREUR : %s", i+1, total, result.index, e)
            return result

        log.info("[%d/%d] #%d (%s) %r exécuté.",
                 i+1, total, result.index, result.action_type, label)

        # Screenshot post-action — toujours capturé (v4)
        if result.x is not None and result.y is not None:
            result.screenshot_b64 = self._capture_screenshot(result.x, result.y)

        # Mesure du temps de réponse
        changed_at = self._wait_for_screen_change(pre_screenshot)
        result.t_screen_changed = changed_at
        if changed_at is not None:
            result.response_time = round(changed_at - result.t_action_sent, 3)
            log.info("    ↳ Temps de réponse : %.3f s", result.response_time)
        else:
            log.info("    ↳ Aucun changement écran dans %.1f s", RESPONSE_WAIT_MAX)

        return result

    # ── Screenshot post-action ────────────────────────────────────────────────

    def _capture_screenshot(self, x: int, y: int) -> Optional[str]:
        try:
            img, _ = screenshot_region(x, y, SCREENSHOT_REGION_PAD)
            buf = io.BytesIO()
            img.save(buf, format="PNG", optimize=True)
            return base64.b64encode(buf.getvalue()).decode()
        except Exception as e:
            log.debug("Échec capture screenshot post-action : %s", e)
            return None

    # ── Vérification OCR ──────────────────────────────────────────────────────

    def _verify_visual(self, x, y, region, expected_text) -> tuple[bool, float]:
        try:
            if x is not None and y is not None:
                img, _ = screenshot_region(x, y, SCREENSHOT_PADDING)
            else:
                rx, ry, rw, rh = region
                img = pyautogui.screenshot(region=(rx, ry, rw, rh))
            results      = self._reader.readtext(np.array(img), detail=0)
            current_text = " | ".join(results).strip()
            score        = difflib.SequenceMatcher(
                None, expected_text.lower(), current_text.lower()
            ).ratio()
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
        elif atype == "middle_click":
            pyautogui.middleClick(x, y)
        elif atype == "drag":
            x2, y2 = raw.get("x2"), raw.get("y2")
            btn = raw.get("button") or "left"
            if x is not None and y is not None:
                pyautogui.moveTo(x, y)
            if x2 is not None and y2 is not None:
                pyautogui.dragTo(x2, y2, duration=0.3, button=btn)
        elif atype == "scroll":
            if x is not None and y is not None:
                pyautogui.moveTo(x, y)
            dy = raw.get("scroll_dy") or 0
            dx = raw.get("scroll_dx") or 0
            if dy:
                pyautogui.scroll(int(dy) * SCROLL_REPLAY_AMOUNT)
            if dx:
                try:
                    pyautogui.hscroll(int(dx) * SCROLL_REPLAY_AMOUNT)
                except Exception:
                    pass
        elif atype == "type":
            if x and y:
                pyautogui.click(x, y)
                time.sleep(0.1)
            pyautogui.typewrite(raw.get("text", ""), interval=0.03)
        elif atype == "key":
            key_map = {
                "enter": "enter", "tab": "tab", "escape": "esc", "space": "space",
                "backspace": "backspace", "delete": "delete",
                "up": "up", "down": "down", "left": "left", "right": "right",
                "home": "home", "end": "end",
                "page_up": "pageup", "page_down": "pagedown",
                "f1": "f1", "f2": "f2", "f3": "f3", "f4": "f4",
                "f5": "f5", "f6": "f6", "f7": "f7", "f8": "f8",
            }
            pyautogui.press(key_map.get(raw.get("key", ""), raw.get("key", "")))
        elif atype == "move":
            if x is not None and y is not None:
                pyautogui.moveTo(x, y, duration=0.05)
        else:
            raise ValueError(f"Type d'action inconnu : {atype!r}")

    # ── Détection de changement d'écran ───────────────────────────────────────

    def _take_full_screenshot(self) -> np.ndarray:
        return np.array(pyautogui.screenshot())

    def _wait_for_screen_change(self, reference: np.ndarray) -> Optional[float]:
        deadline = time.time() + RESPONSE_WAIT_MAX
        ref_gray = np.mean(reference, axis=2).astype(np.float32)
        while time.time() < deadline:
            if self._stop_event.is_set():
                return None
            time.sleep(RESPONSE_POLL_INTERVAL)
            current      = self._take_full_screenshot()
            current_gray = np.mean(current, axis=2).astype(np.float32)
            h = min(ref_gray.shape[0], current_gray.shape[0])
            w = min(ref_gray.shape[1], current_gray.shape[1])
            diff = np.abs(current_gray[:h, :w] - ref_gray[:h, :w])
            if np.mean(diff > 10) >= SCREEN_DIFF_THRESHOLD:
                return time.time()
        return None


# ─── Multi-run ────────────────────────────────────────────────────────────────

class MultiReplayRunner:
    """Lance N fois la même session et persiste tous les résultats en DB."""

    def __init__(
        self,
        ocr_similarity_min:  float = OCR_SIMILARITY_MIN,
        on_run_start: Optional[Callable[[int, int], None]] = None,
        on_run_done:  Optional[Callable[[int, int, list[ActionResult]], None]] = None,
        on_progress:  Optional[Callable[[int, int, ActionResult], None]] = None,
        stop_event:   Optional[threading.Event] = None,
        visual_gate:  bool = False,
        reader=None,
    ):
        self.ocr_similarity_min  = ocr_similarity_min
        self.visual_gate         = visual_gate
        self.reader              = reader
        self.on_run_start        = on_run_start
        self.on_run_done         = on_run_done
        self.on_progress         = on_progress
        self._stop_event         = stop_event or threading.Event()
        self._all_results:  list[list[ActionResult]] = []
        self._all_run_ids:  list[int] = []

    def stop(self):
        self._stop_event.set()

    def run_n_times(
        self,
        session_path: Path,
        n: int,
        interval_s: float = 5.0,
        save_to_db: bool = True,
    ) -> list[list[ActionResult]]:
        self._all_results.clear()
        self._all_run_ids.clear()
        self._stop_event.clear()

        for i in range(n):
            if self._stop_event.is_set():
                log.info("Multi-run interrompu avant run #%d.", i + 1)
                break

            if self.on_run_start:
                self.on_run_start(i + 1, n)
            log.info("═══ Run %d / %d ═══", i + 1, n)

            replayer = ActionReplayer(
                ocr_similarity_min=self.ocr_similarity_min,
                on_progress=self.on_progress,
                visual_gate=self.visual_gate,
                reader=self.reader,
            )
            replayer._stop_event = self._stop_event

            session = replayer.load_session(session_path)
            results = replayer.replay(session)
            self._all_results.append(results)

            if save_to_db:
                run_id = replayer.save_to_db(session_path)
                self._all_run_ids.append(run_id)

            if self.on_run_done:
                self.on_run_done(i + 1, n, results)

            if i < n - 1 and interval_s > 0 and not self._stop_event.is_set():
                log.info("Pause %.1f s avant le prochain run…", interval_s)
                self._stop_event.wait(timeout=interval_s)

        return self._all_results

    @property
    def all_results(self) -> list[list[ActionResult]]:
        return self._all_results

    @property
    def run_ids(self) -> list[int]:
        return self._all_run_ids


# ─── CLI simple ───────────────────────────────────────────────────────────────

def main():
    import sys

    session_path = None
    n_runs   = 1
    interval = 5.0
    visual_gate = False   # v6.3 : gate OCR désactivé par défaut
    args     = sys.argv[1:]

    if args and not args[0].startswith("--"):
        session_path = Path(args.pop(0))
    for a in args:
        if a.startswith("--runs="):
            n_runs = int(a.split("=", 1)[1])
        elif a.startswith("--interval="):
            interval = float(a.split("=", 1)[1])
        elif a in ("--visual-gate", "--ocr"):
            visual_gate = True

    if session_path is None:
        # Cherche d'abord dans scenarios/, puis sessions/
        candidates = sorted(SCENARIOS_DIR.glob("scenario_*.json")) if SCENARIOS_DIR.exists() else []
        if not candidates:
            candidates = sorted(SESSIONS_DIR.glob("session_*.json")) if SESSIONS_DIR.exists() else []
        if not candidates:
            print("Aucune session trouvée dans", SCENARIOS_DIR, "ni", SESSIONS_DIR)
            sys.exit(1)
        session_path = candidates[-1]
        print(f"Dernière session : {session_path}")

    print(f"Gate visuel OCR : {'activé' if visual_gate else 'désactivé (défaut)'}")

    if n_runs == 1:
        rep      = ActionReplayer(visual_gate=visual_gate)
        session  = rep.load_session(session_path)
        rep.replay(session)
        json_p   = rep.save_report(session_path)
        rep.save_to_db(session_path)
        print(f"Rapport → {json_p}")
    else:
        print(f"Multi-run : {n_runs} × {session_path.name} — intervalle {interval}s")
        runner = MultiReplayRunner(visual_gate=visual_gate)
        runner.run_n_times(session_path, n=n_runs, interval_s=interval)
        print(f"Runs terminés. Run IDs : {runner.run_ids}")


if __name__ == "__main__":
    main()
