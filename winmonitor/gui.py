"""
gui.py — Interface graphique Flet de WinGhost Monitor.

Reprend la logique « magnéto » de la v6.6.0 :

  • 🔴 REC      → bascule en « ⏹ STOP REC » (rouge) pendant l'enregistrement
  • ▶️ REPLAY   → bascule en « ⏹ STOP » (rouge) pendant le rejeu
  • 📝 RAPPORT  → (re)génère le dashboard HTML et l'ouvre dans le navigateur

Le journal « Replay live » décrit chaque action rejouée en langage clair et en
temps réel (clic / saisie / touche / déplacement), avec son temps de réponse
visuel et son statut. La liste des scénarios est un accordéon repliable.

Le rejeu et l'enregistrement tournent dans des threads dédiés afin de ne jamais
bloquer l'IHM ; l'arrêt est coopératif (threading.Event pour le rejeu,
Recorder.stop() pour l'enregistrement).
"""

from __future__ import annotations

import threading
import webbrowser
from pathlib import Path

import flet as ft

from version import __version__
from winmonitor import config

# Palette inspirée de l'habillage CHU (bleu / vert / rouge d'action).
_BLUE = "#0091CE"
_GREEN = "#8BC53F"
_RED = "#D64550"
_DARK = "#1E2A38"


# ─── Descriptions humaines (journal « Replay live ») ──────────────────────────
def human_description(action, outcome) -> str:
    t = action.type
    coord = f"({outcome.x}, {outcome.y})" if outcome.x is not None else ""
    if t in ("click", "double_click", "right_click", "middle_click"):
        verb = {
            "click": "Clic", "double_click": "Double-clic",
            "right_click": "Clic droit", "middle_click": "Clic milieu",
        }[t]
        base = f"{verb} en {coord}"
    elif t == "text":
        base = f"Saisie clavier : « {action.text} »"
    elif t == "key":
        base = f"Touche « {action.key} »"
    elif t == "move":
        base = f"Déplacement de la souris vers {coord}"
    elif t == "scroll":
        base = f"Molette ({action.scroll_dy}) en {coord}"
    else:
        base = t
    anchor = "🔍" if outcome.anchored else "📌"
    return f"{base} — {outcome.response_ms:.0f} ms {anchor} [{outcome.status}]"


def _status_color(status: str) -> str:
    return {"ok": _GREEN, "fallback": "#E8A33D", "degraded": "#E8A33D",
            "timeout": _RED}.get(status, _DARK)


class MonitorGUI:
    def __init__(self, page: ft.Page) -> None:
        self.page = page
        self._recording = False
        self._replaying = False
        self._recorder = None
        self._rec_thread = None
        self._replay_thread = None
        self._stop_event = threading.Event()

        config.ensure_dirs()
        self._build()
        self._refresh_scenarios()

    # ─── Construction de l'IHM ────────────────────────────────────────────────
    def _build(self) -> None:
        p = self.page
        p.title = f"WinGhost Monitor v{__version__} — CHU Toulouse"
        p.padding = 16
        try:
            p.window.width, p.window.height = 980, 680
        except Exception:
            pass

        # En-tête.
        header = ft.Container(
            content=ft.Row([
                ft.Text("WinGhost Monitor", size=22, weight=ft.FontWeight.BOLD,
                        color="#FFFFFF"),
                ft.Text(f"v{__version__} · supervision de performance applicative",
                        size=12, color="#E6F4FB"),
            ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
            bgcolor=_BLUE, padding=14, border_radius=10,
        )

        # Barre de transport « magnéto » (3 boutons, logique v6.6).
        self._rec_btn = ft.ElevatedButton(
            "🔴  REC", on_click=self._on_rec, bgcolor=_RED, color="#FFFFFF",
            height=64, expand=True,
        )
        self._replay_btn = ft.ElevatedButton(
            "▶️  REPLAY", on_click=self._on_replay, bgcolor=_GREEN, color=_DARK,
            height=64, expand=True,
        )
        self._report_btn = ft.ElevatedButton(
            "📝  RAPPORT", on_click=self._on_report, bgcolor=_BLUE, color="#FFFFFF",
            height=64, expand=True,
        )
        transport = ft.Row([self._rec_btn, self._replay_btn, self._report_btn],
                           spacing=10)

        # Nom du scénario (pour l'enregistrement).
        self._name_field = ft.TextField(
            label="Nom du scénario à enregistrer", dense=True,
            hint_text="ex. ouverture_dossier_patient",
        )

        # Accordéon « Scénarios » repliable (bouton-titre + panneau).
        self._scen_open = True
        self._scen_toggle = ft.TextButton(
            "📂  Scénarios  ▲", on_click=self._toggle_scenarios,
        )
        self._scen_radio = ft.RadioGroup(content=ft.Column([], tight=True),
                                         on_change=lambda e: None)
        self._scen_panel = ft.Container(content=self._scen_radio, visible=True)

        left = ft.Column([
            transport,
            ft.Divider(height=8, color="transparent"),
            self._name_field,
            ft.Divider(height=8, color="transparent"),
            self._scen_toggle,
            self._scen_panel,
        ], width=380)

        # Journal « Replay live ».
        self._status = ft.Text("Prêt.", size=13, color=_DARK, weight=ft.FontWeight.BOLD)
        self._live = ft.ListView(expand=True, spacing=2, auto_scroll=True)
        right = ft.Column([
            ft.Text("Replay live", size=15, weight=ft.FontWeight.BOLD),
            self._status,
            ft.Container(content=self._live, expand=True, border_radius=8,
                         bgcolor="#F4F8FB", padding=10),
        ], expand=True)

        p.add(header, ft.Divider(height=10, color="transparent"),
              ft.Row([left, ft.VerticalDivider(width=16, color="transparent"), right],
                     expand=True))

    # ─── Scénarios ────────────────────────────────────────────────────────────
    def _discover(self) -> list[str]:
        base = config.SCENARIOS_DIR
        if not base.exists():
            return []
        return sorted(d.name for d in base.iterdir()
                      if (d / "scenario.json").exists())

    def _refresh_scenarios(self) -> None:
        names = self._discover()
        self._scen_radio.content.controls = [
            ft.Radio(value=n, label=n) for n in names
        ] or [ft.Text("Aucun scénario enregistré.", italic=True, color="#888")]
        if names and not self._scen_radio.value:
            self._scen_radio.value = names[0]
        self.page.update()

    def _toggle_scenarios(self, _e) -> None:
        self._scen_open = not self._scen_open
        self._scen_panel.visible = self._scen_open
        self._scen_toggle.text = f"📂  Scénarios  {'▲' if self._scen_open else '▼'}"
        self.page.update()

    # ─── Journal ──────────────────────────────────────────────────────────────
    def _log(self, text: str, color: str = _DARK) -> None:
        self._live.controls.append(ft.Text(text, size=12, color=color,
                                           font_family="Consolas"))
        self.page.update()

    def _set_status(self, text: str, color: str = _DARK) -> None:
        self._status.value = text
        self._status.color = color
        self.page.update()

    # ─── REC (logique v6.6 : bascule REC ↔ STOP REC) ──────────────────────────
    def _on_rec(self, _e) -> None:
        if self._recording:
            self._stop_recording()
        else:
            self._start_recording()

    def _start_recording(self) -> None:
        if self._replaying:
            self._set_status("Rejeu en cours — arrêtez-le avant d'enregistrer.", _RED)
            return
        name = (self._name_field.value or "").strip()
        if not name:
            self._set_status("Saisissez un nom de scénario avant d'enregistrer.", _RED)
            return

        from winmonitor.recorder.listener import Recorder

        self._recorder = Recorder(name)
        self._recording = True
        self._rec_btn.text = "⏹  STOP REC"
        self._rec_btn.bgcolor = "#8C1C24"
        self._set_status(f"Enregistrement de « {name} » — agissez, "
                         f"puis ÉCHAP ou STOP REC.", _RED)

        def worker():
            try:
                self._recorder.start(config.SCENARIOS_DIR)   # bloque jusqu'à stop/ÉCHAP
                path = self._recorder.save(config.SCENARIOS_DIR)
                self._set_status(f"Scénario enregistré : {path.name}", _GREEN)
            except Exception as exc:                          # pragma: no cover
                self._set_status(f"Erreur d'enregistrement : {exc}", _RED)
            finally:
                self._recording = False
                self._rec_btn.text = "🔴  REC"
                self._rec_btn.bgcolor = _RED
                self._refresh_scenarios()

        self._rec_thread = threading.Thread(target=worker, daemon=True)
        self._rec_thread.start()
        self.page.update()

    def _stop_recording(self) -> None:
        if self._recorder is not None:
            self._recorder.stop()

    # ─── REPLAY (logique v6.6 : bascule REPLAY ↔ STOP) ────────────────────────
    def _on_replay(self, _e) -> None:
        if self._replaying:
            self._stop_event.set()
            self._set_status("Arrêt du rejeu demandé…", _RED)
        else:
            self._start_replay()

    def _start_replay(self) -> None:
        if self._recording:
            self._set_status("Enregistrement en cours — arrêtez-le d'abord.", _RED)
            return
        name = self._scen_radio.value
        if not name:
            self._set_status("Sélectionnez un scénario à rejouer.", _RED)
            return

        from winmonitor.kpi.dashboard import build_dashboard
        from winmonitor.kpi.store import MetricsStore
        from winmonitor.recorder.scenario import Scenario
        from winmonitor.replayer.replayer import Replayer

        self._replaying = True
        self._stop_event = threading.Event()
        self._replay_btn.text = "⏹  STOP"
        self._replay_btn.bgcolor = _RED
        self._replay_btn.color = "#FFFFFF"
        self._live.controls.clear()
        self._set_status(f"Rejeu de « {name} »…", _BLUE)
        self.page.update()

        def on_action(action, outcome):
            self._log(human_description(action, outcome),
                      _status_color(outcome.status))

        def worker():
            try:
                folder = Scenario.folder_for(config.SCENARIOS_DIR, name)
                scenario = Scenario.load(folder)
                result = Replayer().run(scenario, folder, on_action=on_action,
                                        stop_event=self._stop_event)
                store = MetricsStore()
                store.insert_run(result)
                build_dashboard(store)
                total = result.total_response_ms
                self._set_status(
                    f"Rejeu terminé [{result.status}] — {total:.0f} ms "
                    f"sur {len(result.outcomes)} action(s).",
                    _status_color(result.status),
                )
            except Exception as exc:                          # pragma: no cover
                self._set_status(f"Erreur de rejeu : {exc}", _RED)
            finally:
                self._replaying = False
                self._replay_btn.text = "▶️  REPLAY"
                self._replay_btn.bgcolor = _GREEN
                self._replay_btn.color = _DARK
                self.page.update()

        self._replay_thread = threading.Thread(target=worker, daemon=True)
        self._replay_thread.start()

    # ─── RAPPORT ──────────────────────────────────────────────────────────────
    def _on_report(self, _e) -> None:
        from winmonitor.kpi.dashboard import build_dashboard

        try:
            path = build_dashboard()
            webbrowser.open(Path(path).resolve().as_uri())
            self._set_status(f"Dashboard ouvert : {path}", _GREEN)
        except Exception as exc:                              # pragma: no cover
            self._set_status(f"Erreur dashboard : {exc}", _RED)


def main(page: ft.Page) -> None:
    MonitorGUI(page)


def run() -> None:
    """Lance l'application Flet (fenêtre desktop)."""
    ft.app(target=main)


if __name__ == "__main__":
    run()
