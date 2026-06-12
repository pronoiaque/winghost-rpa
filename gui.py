"""
gui.py — Interface CustomTkinter pour WinGhost RPA.

v6.1 :
  • Seuil OCR par défaut abaissé à 0.25 (réduit les faux négatifs sur les clics)
  • Titre mis à jour : WinGhost RPA v6.1

v6 :
  • Splash screen au démarrage avec préchargement EasyOCR en arrière-plan
  • Lecteur OCR partagé (`_ocr_reader`) transmis au recorder et au replayer
  • Titre mis à jour : WinGhost RPA v6

v5 :
  • Mode automatique (daemon) : rejoue un scénario en boucle (30 min par défaut)
  • Réduction dans la zone de notification (systray) pendant l'automatique
  • Alerte « gros popup » en cas d'échec d'un cycle
  • Champ « Application cible » pour le journal officiel
  • Dashboard : deux métriques de temps (bout-en-bout + applicatif) avec bulles d'info

v4 :
  • Migration Tkinter → CustomTkinter (thème dark moderne, coins arrondis)
  • Bulles d'aide (CTkToolTip) sur tous les boutons et contrôles
  • Sessions → Scénarios avec noms éditables (rename + delete)
  • Journal Officiel (une ligne par exécution) + Log Debug (toggle)
  • Screenshots toujours activés (plus d'option checkbox)
  • Onglet Stats long-terme corrigé et rafraîchi en temps réel
  • Capture du nom de l'application pour chaque run
  • Multi-run : spinner répétitions + intervalle

v3 conservé : multi-run, SQLite, rapport HTML/SVG, dashboard Flask
"""

import datetime
import json
import os
import subprocess
import sys
import threading
import time
import webbrowser
from pathlib import Path

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

try:
    import customtkinter as ctk
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("blue")
except ImportError:
    print("customtkinter requis : pip install customtkinter", file=sys.stderr)
    sys.exit(1)

try:
    import easyocr as _easyocr
    _HAS_EASYOCR = True
except ImportError:
    _HAS_EASYOCR = False

try:
    from recorder import ActionRecorder, get_all_monitors, SCENARIOS_DIR
    from replayer import (ActionReplayer, ActionResult, MultiReplayRunner,
                          REPORTS_DIR)
    from scheduler import SchedulerRunner
    import stats_db
    import official_log
except ImportError as e:
    ctk.CTkMessagebox = None
    messagebox.showerror("Import manquant", str(e))
    sys.exit(1)

# Systray (mode automatique) — optionnel, repli sur la barre des tâches si absent
try:
    import pystray
    from PIL import Image as _PILImage, ImageDraw as _PILDraw
    _HAS_TRAY = True
except Exception:
    _HAS_TRAY = False

# Compat : chercher scénarios dans les deux dossiers (migration v3→v4)
_LEGACY_SESSIONS_DIR = Path("sessions")
SCENARIOS_DIR_LOCAL  = SCENARIOS_DIR  # Path("scenarios")

# ─── Palette ──────────────────────────────────────────────────────────────────

_BG        = "#1A1D27"
_BG2       = "#22263A"
_BG3       = "#2A2E42"
_BG4       = "#343850"
_ACCENT    = "#5B8DEF"
_ACCENT2   = "#F09058"
_GREEN     = "#43C59E"
_RED       = "#E05C6A"
_YELLOW    = "#E0B84A"
_FG        = "#D8DEE9"
_FG2       = "#7B8496"

_FONT_MONO = ("Consolas", 9)
_FONT_UI   = ("Segoe UI", 11)
_FONT_SM   = ("Segoe UI", 10)
_FONT_H1   = ("Segoe UI Semibold", 14)

_SERVER_PORT = 5000
_SERVER_PROC = None


# ─── Tooltip ──────────────────────────────────────────────────────────────────

class CTkToolTip:
    """Bulle d'aide légère compatible avec tous les widgets CTk/Tk."""
    _delay = 600  # ms avant apparition

    def __init__(self, widget: tk.BaseWidget, text: str):
        self._widget  = widget
        self._text    = text
        self._popup   = None
        self._job     = None
        widget.bind("<Enter>",   self._on_enter, add="+")
        widget.bind("<Leave>",   self._on_leave, add="+")
        widget.bind("<ButtonPress>", self._on_leave, add="+")

    def _on_enter(self, event):
        self._job = self._widget.after(self._delay, self._show, event)

    def _on_leave(self, _event=None):
        if self._job:
            self._widget.after_cancel(self._job)
            self._job = None
        if self._popup:
            self._popup.destroy()
            self._popup = None

    def _show(self, event):
        x = self._widget.winfo_rootx() + 20
        y = self._widget.winfo_rooty() + self._widget.winfo_height() + 4
        self._popup = tk.Toplevel(self._widget)
        self._popup.wm_overrideredirect(True)
        self._popup.wm_geometry(f"+{x}+{y}")
        self._popup.wm_attributes("-topmost", True)
        frm = tk.Frame(self._popup, background=_BG3,
                       highlightthickness=1, highlightbackground=_ACCENT)
        frm.pack()
        tk.Label(frm, text=self._text, background=_BG3, foreground=_FG,
                 font=("Segoe UI", 9), padx=10, pady=5,
                 wraplength=280, justify="left").pack()


# ─── Spinbox custom ───────────────────────────────────────────────────────────

class _Spinbox(ctk.CTkFrame):
    def __init__(self, parent, from_=1, to=99, initial=1, width=120, **kw):
        super().__init__(parent, fg_color="transparent", **kw)
        self._var  = tk.IntVar(value=initial)
        self._from = from_
        self._to   = to
        ctk.CTkButton(self, text="−", width=28, height=28,
                      fg_color=_BG4, hover_color=_BG3, text_color=_FG,
                      command=lambda: self._step(-1)).pack(side="left")
        ctk.CTkEntry(self, textvariable=self._var, width=width - 60,
                     height=28, justify="center", font=_FONT_SM,
                     fg_color=_BG3, border_color=_BG4,
                     text_color=_FG).pack(side="left", padx=3)
        ctk.CTkButton(self, text="+", width=28, height=28,
                      fg_color=_BG4, hover_color=_BG3, text_color=_FG,
                      command=lambda: self._step(1)).pack(side="left")

    def _step(self, d):
        self._var.set(max(self._from, min(self._to, self._var.get() + d)))

    def get(self) -> int:
        return self._var.get()

    def set(self, v: int):
        self._var.set(v)


# ─── Ligne de scénario ────────────────────────────────────────────────────────

class _ScenarioRow(ctk.CTkFrame):
    """Une ligne dans la liste des scénarios : nom + badge runs + boutons."""

    _COLOR_NORMAL   = _BG3
    _COLOR_SELECTED = "#2C3866"

    def __init__(self, parent, scenario_path: Path, run_count: int,
                 on_select, on_delete, on_rename, **kw):
        super().__init__(parent, fg_color=self._COLOR_NORMAL,
                         corner_radius=6, **kw)
        self.scenario_path = scenario_path
        self._on_select    = on_select
        self._selected     = False

        # Lire le nom du scénario depuis le JSON (champ scenario_name)
        self._display_name = self._read_scenario_name(scenario_path)

        # Colonne principale cliquable
        inner = ctk.CTkFrame(self, fg_color="transparent")
        inner.pack(side="left", fill="both", expand=True,
                   padx=(8, 0), pady=4)

        icon = ctk.CTkLabel(inner, text="🎬", font=("Segoe UI", 11),
                             text_color=_ACCENT2, width=20)
        icon.pack(side="left")
        icon.bind("<Button-1>", lambda _: on_select(scenario_path))

        self._name_lbl = ctk.CTkLabel(
            inner, text=self._display_name,
            font=_FONT_SM, text_color=_FG,
            anchor="w",
        )
        self._name_lbl.pack(side="left", padx=(6, 0), fill="x", expand=True)
        self._name_lbl.bind("<Button-1>", lambda _: on_select(scenario_path))

        # Badge nombre de runs
        if run_count > 0:
            badge = ctk.CTkLabel(
                self, text=f"{run_count}▸", font=("Segoe UI", 9),
                text_color=_FG2, width=30,
            )
            badge.pack(side="right", padx=(0, 2))

        # Bouton renommer
        btn_rename = ctk.CTkButton(
            self, text="✎", width=24, height=24,
            fg_color="transparent", hover_color=_BG4,
            text_color=_FG2, font=("Segoe UI", 11),
            command=lambda: on_rename(scenario_path, self),
        )
        btn_rename.pack(side="right")
        CTkToolTip(btn_rename, "Renommer ce scénario")

        # Bouton supprimer
        btn_del = ctk.CTkButton(
            self, text="🗑", width=24, height=24,
            fg_color="transparent", hover_color="#3D1F22",
            text_color=_RED, font=("Segoe UI", 11),
            command=lambda: on_delete(scenario_path),
        )
        btn_del.pack(side="right", padx=(0, 2))
        CTkToolTip(btn_del, "Supprimer ce scénario définitivement")

    @staticmethod
    def _read_scenario_name(path: Path) -> str:
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            return data.get("scenario_name") or path.stem
        except Exception:
            return path.stem

    def set_selected(self, selected: bool):
        self._selected = selected
        self.configure(fg_color=self._COLOR_SELECTED if selected else self._COLOR_NORMAL)

    def update_name(self, new_name: str):
        self._display_name = new_name
        self._name_lbl.configure(text=new_name)


# ─── Application principale ───────────────────────────────────────────────────

class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("WinGhost RPA v6.1")
        self.configure(fg_color=_BG)
        self.minsize(1000, 700)
        self._center_window(1060, 740)

        self._ocr_reader = None
        self._recorder: ActionRecorder | None  = None
        self._replayer: ActionReplayer | None  = None
        self._multi_runner: MultiReplayRunner | None = None
        self._session_path: Path | None = None
        self._replay_thread: threading.Thread | None = None
        self._results: list[ActionResult] = []
        self._report_json_path: Path | None = None
        self._report_html_path: Path | None = None
        self._current_run_index  = 0
        self._total_runs_planned = 1
        self._scenario_rows: list[_ScenarioRow] = []

        # Mode automatique (daemon) + systray
        self._scheduler: SchedulerRunner | None = None
        self._auto_thread: threading.Thread | None = None
        self._auto_running = False
        self._tray_icon = None

        stats_db.init_db()
        official_log.init_logs()
        self.withdraw()           # caché jusqu'à la fin du splash
        self._build_ui()
        self._refresh_scenario_list()
        self.after(300, self._update_monitor_status)
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.after(20, self._show_splash)

    # ── Centrage ──────────────────────────────────────────────────────────────

    def _center_window(self, w: int, h: int):
        try:
            monitors = get_all_monitors()
            m = monitors[0]
            x = m["left"] + (m["width"]  - w) // 2
            y = m["top"]  + (m["height"] - h) // 2
        except Exception:
            x = y = 100
        self.geometry(f"{w}x{h}+{x}+{y}")

    def _show_splash(self):
        """Affiche le splash screen et précharge EasyOCR en arrière-plan."""
        splash = ctk.CTkToplevel(self)
        splash.title("WinGhost RPA")
        splash.resizable(False, False)
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        w, h = 480, 260
        splash.geometry(f"{w}x{h}+{(sw - w) // 2}+{(sh - h) // 2}")
        splash.configure(fg_color=_BG2)
        splash.attributes("-topmost", True)
        try:
            splash.overrideredirect(True)
        except Exception:
            pass
        splash.lift()

        ctk.CTkLabel(splash, text="🤖  WinGhost RPA",
                     font=("Segoe UI Bold", 26), text_color=_ACCENT).pack(pady=(36, 4))
        ctk.CTkLabel(splash, text="v6.1 — Robot Process Automation",
                     font=("Segoe UI", 12), text_color=_FG2).pack()
        ctk.CTkLabel(splash, text="© WinGhost 2026",
                     font=("Segoe UI", 9), text_color=_FG2).pack(side="bottom", pady=10)

        frm = ctk.CTkFrame(splash, fg_color="transparent")
        frm.pack(fill="x", padx=48, pady=(24, 0))
        status_lbl = ctk.CTkLabel(frm, text="Démarrage…", font=_FONT_SM,
                                   text_color=_FG2, anchor="w")
        status_lbl.pack(fill="x", pady=(0, 6))
        bar = ctk.CTkProgressBar(frm, fg_color=_BG3, progress_color=_ACCENT,
                                  mode="indeterminate", height=6)
        bar.pack(fill="x")
        bar.start()

        def _step(text: str, done: bool = False):
            try:
                splash.after(0, lambda: status_lbl.configure(text=text))
                if done:
                    splash.after(0, bar.stop)
                    splash.after(0, lambda: bar.configure(mode="determinate"))
                    splash.after(0, lambda: bar.set(1.0))
            except Exception:
                pass

        def _load():
            _step("Initialisation EasyOCR…")
            if _HAS_EASYOCR:
                self._ocr_reader = _easyocr.Reader(
                    ["fr", "en"], gpu=False, verbose=False)
            _step("EasyOCR prêt ✓", done=True)
            time.sleep(0.5)
            self.after(0, _done)

        def _done():
            try:
                splash.destroy()
            except Exception:
                pass
            self.deiconify()
            self.lift()

        threading.Thread(target=_load, daemon=True).start()

    # ── Construction UI ───────────────────────────────────────────────────────

    def _build_ui(self):
        # ── Header ───────────────────────────────────────────────────────────
        header = ctk.CTkFrame(self, fg_color=_BG2, corner_radius=0, height=52)
        header.pack(fill="x")
        header.pack_propagate(False)

        ctk.CTkLabel(header, text="🤖  WinGhost RPA v6.1",
                     font=_FONT_H1, text_color=_ACCENT).pack(
            side="left", padx=20)

        self._monitor_var = tk.StringVar(value="")
        ctk.CTkLabel(header, textvariable=self._monitor_var,
                     font=_FONT_SM, text_color=_FG2).pack(side="right", padx=16)

        self._status_var = tk.StringVar(value="Prêt")
        ctk.CTkLabel(header, textvariable=self._status_var,
                     font=_FONT_SM, text_color=_FG2).pack(side="right", padx=(0, 10))

        # ── Corps principal ───────────────────────────────────────────────────
        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=16, pady=12)

        left = ctk.CTkFrame(body, fg_color="transparent", width=290)
        left.pack(side="left", fill="y", padx=(0, 12))
        left.pack_propagate(False)

        right = ctk.CTkFrame(body, fg_color="transparent")
        right.pack(side="left", fill="both", expand=True)

        self._build_left(left)
        self._build_right(right)

    # ── Panneau gauche ────────────────────────────────────────────────────────

    def _build_left(self, parent):
        # RECORD
        rec = ctk.CTkFrame(parent, fg_color=_BG2, corner_radius=10)
        rec.pack(fill="x", pady=(0, 10))

        ctk.CTkLabel(rec, text="⬤  Enregistrement",
                     font=_FONT_SM, text_color=_FG2).pack(
            anchor="w", padx=12, pady=(10, 4))

        # Nom du scénario
        name_row = ctk.CTkFrame(rec, fg_color="transparent")
        name_row.pack(fill="x", padx=10, pady=(0, 6))
        ctk.CTkLabel(name_row, text="Nom :", font=_FONT_SM,
                     text_color=_FG2, width=44).pack(side="left")
        self._scenario_name_entry = ctk.CTkEntry(
            name_row, placeholder_text="Mon scénario…",
            font=_FONT_SM, fg_color=_BG3, border_color=_BG4,
            text_color=_FG, height=28,
        )
        self._scenario_name_entry.pack(side="left", fill="x", expand=True)
        CTkToolTip(self._scenario_name_entry,
                   "Nom du scénario qui sera enregistré")

        # Application cible
        app_row = ctk.CTkFrame(rec, fg_color="transparent")
        app_row.pack(fill="x", padx=10, pady=(0, 6))
        ctk.CTkLabel(app_row, text="App :", font=_FONT_SM,
                     text_color=_FG2, width=44).pack(side="left")
        self._target_app_entry = ctk.CTkEntry(
            app_row, placeholder_text="Ex : Outlook, O…",
            font=_FONT_SM, fg_color=_BG3, border_color=_BG4,
            text_color=_FG, height=28,
        )
        self._target_app_entry.pack(side="left", fill="x", expand=True)
        CTkToolTip(self._target_app_entry,
                   "Nom de l'application ciblée par ce scénario\n"
                   "Inscrit tel quel dans le journal officiel\n"
                   "(laisser vide = détection auto du processus actif)")

        self._rec_btn = ctk.CTkButton(
            rec, text="  ⬤  RECORD",
            font=("Segoe UI Semibold", 12),
            fg_color=_GREEN, hover_color="#35A07E", text_color=_BG,
            height=36, corner_radius=8,
            command=self._toggle_record,
        )
        self._rec_btn.pack(fill="x", padx=10, pady=(0, 10))
        CTkToolTip(self._rec_btn,
                   "Démarrer l'enregistrement des actions souris/clavier\n"
                   "Cliquer à nouveau pour arrêter et sauvegarder")

        # SCÉNARIOS
        scen_frame = ctk.CTkFrame(parent, fg_color=_BG2, corner_radius=10)
        scen_frame.pack(fill="both", expand=True, pady=(0, 10))

        hdr = ctk.CTkFrame(scen_frame, fg_color="transparent")
        hdr.pack(fill="x", padx=10, pady=(10, 4))
        ctk.CTkLabel(hdr, text="▶  Scénarios",
                     font=_FONT_SM, text_color=_FG2).pack(side="left")
        rf = ctk.CTkButton(hdr, text="↺", width=26, height=24,
                           fg_color="transparent", hover_color=_BG4,
                           text_color=_FG2, font=("Segoe UI", 12),
                           command=self._refresh_scenario_list)
        rf.pack(side="right")
        CTkToolTip(rf, "Rafraîchir la liste des scénarios")

        self._scen_scroll = ctk.CTkScrollableFrame(
            scen_frame, fg_color=_BG3, corner_radius=6,
            scrollbar_button_color=_BG4,
            scrollbar_button_hover_color=_ACCENT,
        )
        self._scen_scroll.pack(fill="both", expand=True, padx=8, pady=(0, 6))

        browse_btn = ctk.CTkButton(
            scen_frame, text="Parcourir…", height=26,
            fg_color=_BG3, hover_color=_BG4, text_color=_FG2,
            font=_FONT_SM, corner_radius=6,
            command=self._browse_scenario,
        )
        browse_btn.pack(fill="x", padx=10, pady=(0, 8))
        CTkToolTip(browse_btn, "Ouvrir un fichier scénario JSON depuis un autre dossier")

        # OPTIONS
        opt = ctk.CTkFrame(parent, fg_color=_BG2, corner_radius=10)
        opt.pack(fill="x", pady=(0, 10))
        ctk.CTkLabel(opt, text="⚙  Options replay",
                     font=_FONT_SM, text_color=_FG2).pack(
            anchor="w", padx=12, pady=(10, 4))

        # Seuil OCR
        ocr_row = ctk.CTkFrame(opt, fg_color="transparent")
        ocr_row.pack(fill="x", padx=10, pady=2)
        ctk.CTkLabel(ocr_row, text="Seuil OCR", font=_FONT_SM,
                     text_color=_FG2, width=90).pack(side="left")
        self._ocr_threshold_var = tk.DoubleVar(value=0.25)
        ocr_lbl = ctk.CTkLabel(ocr_row, textvariable=tk.StringVar(),
                                font=_FONT_SM, text_color=_FG, width=36)
        ocr_lbl.pack(side="right")
        ocr_slider = ctk.CTkSlider(
            ocr_row, variable=self._ocr_threshold_var,
            from_=0.0, to=1.0, number_of_steps=20,
            button_color=_ACCENT, button_hover_color=_ACCENT,
            progress_color=_ACCENT, fg_color=_BG3,
            command=lambda v: ocr_lbl.configure(text=f"{v:.2f}"),
        )
        ocr_slider.pack(side="left", fill="x", expand=True, padx=6)
        ocr_lbl.configure(text=f"{self._ocr_threshold_var.get():.2f}")
        CTkToolTip(ocr_slider,
                   "Score minimum de similarité OCR pour valider une action\n"
                   "0.0 = jamais ignorer · 1.0 = correspondance parfaite requise")

        # Répétitions
        rep_row = ctk.CTkFrame(opt, fg_color="transparent")
        rep_row.pack(fill="x", padx=10, pady=2)
        ctk.CTkLabel(rep_row, text="Répétitions", font=_FONT_SM,
                     text_color=_FG2, width=90).pack(side="left")
        self._spin_runs = _Spinbox(rep_row, from_=1, to=99, initial=1, width=110)
        self._spin_runs.pack(side="left")
        CTkToolTip(self._spin_runs,
                   "Nombre de fois où rejouer le scénario consécutivement\n"
                   "Les stats de chaque run sont sauvegardées séparément")

        # Intervalle
        int_row = ctk.CTkFrame(opt, fg_color="transparent")
        int_row.pack(fill="x", padx=10, pady=(2, 10))
        ctk.CTkLabel(int_row, text="Intervalle (s)", font=_FONT_SM,
                     text_color=_FG2, width=90).pack(side="left")
        self._interval_var = tk.DoubleVar(value=5.0)
        int_entry = ctk.CTkEntry(int_row, textvariable=self._interval_var,
                                  width=70, height=28, justify="center",
                                  font=_FONT_SM, fg_color=_BG3,
                                  border_color=_BG4, text_color=_FG)
        int_entry.pack(side="left", padx=6)
        CTkToolTip(int_entry,
                   "Pause en secondes entre deux runs consécutifs\n"
                   "Utile pour laisser l'application se réinitialiser")

        # BOUTONS D'ACTION
        self._replay_btn = ctk.CTkButton(
            parent, text="  ▶  REPLAY",
            font=("Segoe UI Semibold", 12),
            fg_color=_ACCENT, hover_color="#4070CC", text_color=_BG,
            height=38, corner_radius=8,
            state="disabled",
            command=self._start_replay,
        )
        self._replay_btn.pack(fill="x", pady=(0, 6))
        CTkToolTip(self._replay_btn,
                   "Lancer le replay du scénario sélectionné\n"
                   "Vérifie visuellement chaque action via OCR avant de l'exécuter")

        self._stop_btn = ctk.CTkButton(
            parent, text="  ■  STOP",
            font=("Segoe UI Semibold", 12),
            fg_color=_RED, hover_color="#B04050", text_color=_BG,
            height=38, corner_radius=8,
            state="disabled",
            command=self._stop_replay,
        )
        self._stop_btn.pack(fill="x", pady=(0, 6))
        CTkToolTip(self._stop_btn,
                   "Arrêter le replay en cours après l'action courante\n"
                   "Les résultats déjà collectés seront sauvegardés")

        self._dashboard_btn = ctk.CTkButton(
            parent, text="  🌐  Dashboard Web",
            font=_FONT_SM,
            fg_color=_BG3, hover_color=_BG4, text_color=_ACCENT,
            height=34, corner_radius=8,
            command=self._open_dashboard,
        )
        self._dashboard_btn.pack(fill="x", pady=(0, 6))
        CTkToolTip(self._dashboard_btn,
                   "Ouvrir le dashboard Flask dans le navigateur\n"
                   f"http://127.0.0.1:{_SERVER_PORT}/\n"
                   "Graphiques, heatmap horaire, export CSV")

        # MODE AUTOMATIQUE (daemon)
        auto = ctk.CTkFrame(parent, fg_color=_BG2, corner_radius=10)
        auto.pack(fill="x")
        ctk.CTkLabel(auto, text="🔁  Mode automatique",
                     font=_FONT_SM, text_color=_FG2).pack(
            anchor="w", padx=12, pady=(8, 2))

        ai_row = ctk.CTkFrame(auto, fg_color="transparent")
        ai_row.pack(fill="x", padx=10, pady=2)
        ctk.CTkLabel(ai_row, text="Intervalle (min)", font=_FONT_SM,
                     text_color=_FG2, width=100).pack(side="left")
        self._auto_interval_var = tk.DoubleVar(value=30.0)
        ai_entry = ctk.CTkEntry(ai_row, textvariable=self._auto_interval_var,
                                width=64, height=28, justify="center",
                                font=_FONT_SM, fg_color=_BG3,
                                border_color=_BG4, text_color=_FG)
        ai_entry.pack(side="left", padx=6)
        CTkToolTip(ai_entry,
                   "Délai entre deux exécutions automatiques\n"
                   "Spec métier : 30 minutes")

        self._auto_btn = ctk.CTkButton(
            auto, text="  ⏱  Démarrer l'automatique",
            font=_FONT_SM,
            fg_color=_ACCENT2, hover_color="#C9733F", text_color=_BG,
            height=34, corner_radius=8,
            command=self._toggle_auto,
        )
        self._auto_btn.pack(fill="x", padx=10, pady=(4, 4))
        CTkToolTip(self._auto_btn,
                   "Rejoue le scénario sélectionné en boucle, à intervalle régulier\n"
                   "La fenêtre se réduit dans la zone de notification (systray)\n"
                   "Une alerte s'affiche en cas d'échec d'un cycle")

        self._auto_status_lbl = ctk.CTkLabel(
            auto, text="", font=("Segoe UI", 9), text_color=_ACCENT2)
        self._auto_status_lbl.pack(anchor="w", padx=12, pady=(0, 8))

    # ── Panneau droit ─────────────────────────────────────────────────────────

    def _build_right(self, parent):
        # Barre de progression
        prog_row = ctk.CTkFrame(parent, fg_color="transparent", height=32)
        prog_row.pack(fill="x", pady=(0, 8))
        prog_row.pack_propagate(False)

        self._run_lbl = ctk.CTkLabel(prog_row, text="",
                                      font=_FONT_SM, text_color=_ACCENT2, width=80)
        self._run_lbl.pack(side="left")

        self._progress_var = tk.DoubleVar(value=0)
        self._progress_bar = ctk.CTkProgressBar(
            prog_row, variable=self._progress_var,
            progress_color=_ACCENT, fg_color=_BG3, height=8,
        )
        self._progress_bar.set(0)
        self._progress_bar.pack(side="left", fill="x", expand=True, padx=8)

        self._progress_lbl = ctk.CTkLabel(prog_row, text="",
                                           font=_FONT_SM, text_color=_FG2, width=60)
        self._progress_lbl.pack(side="left")

        # Onglets principaux
        self._tabs = ctk.CTkTabview(
            parent,
            fg_color=_BG2,
            segmented_button_fg_color=_BG3,
            segmented_button_selected_color=_ACCENT,
            segmented_button_selected_hover_color="#4070CC",
            segmented_button_unselected_color=_BG3,
            segmented_button_unselected_hover_color=_BG4,
            text_color=_FG,
            text_color_disabled=_FG2,
            corner_radius=10,
        )
        self._tabs.pack(fill="both", expand=True)
        self._tabs.add("Journal")
        self._tabs.add("Rapport")
        self._tabs.add("Stats long-terme")
        self._tabs._segmented_button.configure(font=_FONT_SM)

        # Rafraîchit les stats lors du changement d'onglet
        try:
            self._tabs._segmented_button.configure(
                command=lambda _tab: self.after(100, self._on_tab_changed))
        except Exception:
            pass

        self._build_journal_tab(self._tabs.tab("Journal"))
        self._build_report_tab(self._tabs.tab("Rapport"))
        self._build_stats_tab(self._tabs.tab("Stats long-terme"))

    def _build_journal_tab(self, parent):
        # Sous-onglets : Officiel / Debug
        self._log_tabs = ctk.CTkTabview(
            parent,
            fg_color=_BG3,
            segmented_button_fg_color=_BG4,
            segmented_button_selected_color=_BG2,
            segmented_button_unselected_color=_BG4,
            segmented_button_unselected_hover_color=_BG3,
            text_color=_FG,
            corner_radius=8,
            height=28,
        )
        self._log_tabs.pack(fill="both", expand=True, padx=4, pady=4)
        self._log_tabs.add("Journal officiel")
        self._log_tabs.add("Log debug")
        self._log_tabs._segmented_button.configure(font=_FONT_SM)

        # Journal officiel
        off_tab = self._log_tabs.tab("Journal officiel")
        off_top = ctk.CTkFrame(off_tab, fg_color="transparent")
        off_top.pack(fill="x", pady=(0, 4))
        ctk.CTkLabel(off_top,
                     text="Une ligne par exécution complète  ·  app ; scénario ; durée ; statut",
                     font=("Segoe UI", 9), text_color=_FG2).pack(side="left")
        exp_csv = ctk.CTkButton(off_top, text="⬇ CSV officiel", height=24, width=100,
                                 fg_color=_BG4, hover_color=_BG3, text_color=_FG2,
                                 font=_FONT_SM, corner_radius=6,
                                 command=self._export_official_csv)
        exp_csv.pack(side="right")
        CTkToolTip(exp_csv, "Exporter le journal officiel du mois courant en CSV")

        self._official_log_box = ctk.CTkTextbox(
            off_tab, font=_FONT_MONO,
            fg_color=_BG3, text_color=_FG,
            state="disabled", corner_radius=6,
        )
        self._official_log_box.pack(fill="both", expand=True)
        # Tags via le widget Text interne
        self._official_log_box._textbox.tag_configure("ok",   foreground=_GREEN)
        self._official_log_box._textbox.tag_configure("warn", foreground=_YELLOW)
        self._official_log_box._textbox.tag_configure("err",  foreground=_RED)
        self._official_log_box._textbox.tag_configure("head", foreground=_ACCENT,
                                                       font=("Consolas", 9, "bold"))

        # Log debug
        dbg_tab = self._log_tabs.tab("Log debug")
        ctk.CTkLabel(dbg_tab,
                     text="Détail action-par-action (OCR, timing, erreurs)",
                     font=("Segoe UI", 9), text_color=_FG2).pack(anchor="w", pady=(0, 4))
        self._debug_log_box = ctk.CTkTextbox(
            dbg_tab, font=_FONT_MONO,
            fg_color=_BG3, text_color=_FG,
            state="disabled", corner_radius=6,
        )
        self._debug_log_box.pack(fill="both", expand=True)
        for tag, fg in [("ok", _GREEN), ("warn", _YELLOW), ("error", _RED),
                        ("info", _FG2), ("heading", _ACCENT), ("run", _ACCENT2)]:
            kw = {"foreground": fg}
            if tag in ("heading", "run"):
                kw["font"] = ("Consolas", 9, "bold")
            self._debug_log_box._textbox.tag_configure(tag, **kw)

        # Charger les entrées existantes du journal officiel
        self.after(500, self._load_official_log)

    def _build_report_tab(self, parent):
        cols = ("#", "Type", "Cible", "OCR", "Visuel", "Réponse (ms)", "Statut")
        frame = ctk.CTkFrame(parent, fg_color=_BG3, corner_radius=8)
        frame.pack(fill="both", expand=True, padx=4, pady=4)

        sb = tk.Scrollbar(frame)
        sb.pack(side="right", fill="y")

        style = ttk.Style()
        style.theme_use("clam")
        style.configure("V4.Treeview",
                         background=_BG3, fieldbackground=_BG3,
                         foreground=_FG, rowheight=22,
                         font=_FONT_MONO, borderwidth=0)
        style.configure("V4.Treeview.Heading",
                         background=_BG4, foreground=_ACCENT,
                         font=("Segoe UI Semibold", 9), relief="flat")
        style.map("V4.Treeview",
                  background=[("selected", _ACCENT)],
                  foreground=[("selected", _BG)])

        self._tree = ttk.Treeview(frame, columns=cols, show="headings",
                                   style="V4.Treeview", yscrollcommand=sb.set)
        for col in cols:
            self._tree.heading(col, text=col)
        self._tree.column("#",            width=40,  stretch=False)
        self._tree.column("Type",         width=100, stretch=False)
        self._tree.column("Cible",        width=180, stretch=True)
        self._tree.column("OCR",          width=60,  stretch=False)
        self._tree.column("Visuel",       width=60,  stretch=False)
        self._tree.column("Réponse (ms)", width=100, stretch=False)
        self._tree.column("Statut",       width=150, stretch=True)
        sb.config(command=self._tree.yview)
        self._tree.pack(fill="both", expand=True)

        for tag, fg in [("ok", _GREEN), ("warn", _YELLOW), ("error", _RED)]:
            self._tree.tag_configure(tag, foreground=fg)

        foot = ctk.CTkFrame(parent, fg_color="transparent")
        foot.pack(fill="x", padx=4, pady=(4, 0))

        self._report_summary_lbl = ctk.CTkLabel(
            foot, text="", font=_FONT_SM, text_color=_FG2, anchor="w")
        self._report_summary_lbl.pack(side="left")

        btn_folder = ctk.CTkButton(foot, text="📂 Rapports", height=28, width=100,
                                    fg_color=_BG3, hover_color=_BG4,
                                    text_color=_FG2, font=_FONT_SM, corner_radius=6,
                                    command=lambda: self._open_folder(REPORTS_DIR))
        btn_folder.pack(side="right")
        CTkToolTip(btn_folder, "Ouvrir le dossier des rapports dans l'explorateur")

        btn_json = ctk.CTkButton(foot, text="JSON", height=28, width=60,
                                  fg_color=_BG3, hover_color=_BG4,
                                  text_color=_FG2, font=_FONT_SM, corner_radius=6,
                                  command=self._export_report_json)
        btn_json.pack(side="right", padx=(0, 4))
        CTkToolTip(btn_json, "Exporter les résultats du dernier replay en JSON")

        btn_html = ctk.CTkButton(foot, text="🌐 HTML", height=28, width=80,
                                  fg_color=_ACCENT, hover_color="#4070CC",
                                  text_color=_BG, font=_FONT_SM, corner_radius=6,
                                  command=self._export_report_html)
        btn_html.pack(side="right", padx=(0, 4))
        CTkToolTip(btn_html,
                   "Générer un rapport HTML avec graphique SVG\n"
                   "et screenshots inline, puis l'ouvrir dans le navigateur")

    def _build_stats_tab(self, parent):
        # Sélecteur de session
        top = ctk.CTkFrame(parent, fg_color="transparent")
        top.pack(fill="x", padx=4, pady=(4, 6))

        ctk.CTkLabel(top, text="Scénario :", font=_FONT_SM,
                     text_color=_FG2).pack(side="left")

        self._stats_session_var = tk.StringVar()
        self._stats_session_cb  = ctk.CTkComboBox(
            top, variable=self._stats_session_var,
            values=[], state="readonly", width=300,
            font=_FONT_SM, fg_color=_BG3, border_color=_BG4,
            button_color=_BG4, button_hover_color=_ACCENT,
            dropdown_fg_color=_BG3, dropdown_text_color=_FG,
            dropdown_hover_color=_BG4,
            command=lambda _: self._refresh_stats(),
        )
        self._stats_session_cb.pack(side="left", padx=8)
        CTkToolTip(self._stats_session_cb,
                   "Sélectionner le scénario à analyser dans la base de données")

        btn_refresh = ctk.CTkButton(top, text="🔄", width=32, height=30,
                                     fg_color=_BG3, hover_color=_BG4,
                                     text_color=_FG2, font=_FONT_SM, corner_radius=6,
                                     command=self._refresh_stats_full)
        btn_refresh.pack(side="left")
        CTkToolTip(btn_refresh, "Actualiser les statistiques depuis la base SQLite")

        btn_csv = ctk.CTkButton(top, text="⬇ CSV", height=30, width=70,
                                 fg_color=_GREEN, hover_color="#35A07E",
                                 text_color=_BG, font=_FONT_SM, corner_radius=6,
                                 command=self._export_csv)
        btn_csv.pack(side="left", padx=6)
        CTkToolTip(btn_csv,
                   "Exporter tous les runs de ce scénario en CSV\n"
                   "Compatible Excel (UTF-8 BOM)")

        btn_web = ctk.CTkButton(top, text="🌐 Dashboard", height=30, width=100,
                                 fg_color=_BG3, hover_color=_BG4,
                                 text_color=_ACCENT, font=_FONT_SM, corner_radius=6,
                                 command=self._open_dashboard)
        btn_web.pack(side="right")
        CTkToolTip(btn_web, "Ouvrir le dashboard web avec graphiques dynamiques")

        # Sous-onglets
        self._stats_tabs = ctk.CTkTabview(
            parent,
            fg_color=_BG3,
            segmented_button_fg_color=_BG4,
            segmented_button_selected_color=_BG2,
            segmented_button_unselected_color=_BG4,
            segmented_button_unselected_hover_color=_BG3,
            text_color=_FG,
            corner_radius=8,
        )
        self._stats_tabs.pack(fill="both", expand=True, padx=4)
        self._stats_tabs.add("Historique des runs")
        self._stats_tabs.add("Stats par bouton")
        self._stats_tabs._segmented_button.configure(font=_FONT_SM)

        # Treeview runs
        runs_frame = ctk.CTkFrame(self._stats_tabs.tab("Historique des runs"),
                                   fg_color=_BG3, corner_radius=6)
        runs_frame.pack(fill="both", expand=True)
        run_cols = ("Run", "Démarré le", "App", "Total", "OK", "Ignorées",
                    "Erreurs", "Avg ms", "Max ms", "Durée s")
        sb_r = tk.Scrollbar(runs_frame)
        sb_r.pack(side="right", fill="y")
        self._runs_tree = ttk.Treeview(runs_frame, columns=run_cols,
                                        show="headings", style="V4.Treeview",
                                        yscrollcommand=sb_r.set)
        for c in run_cols:
            self._runs_tree.heading(c, text=c)
        for c, w in [("Run", 50), ("Démarré le", 145), ("App", 100),
                     ("Total", 55), ("OK", 45), ("Ignorées", 70),
                     ("Erreurs", 65), ("Avg ms", 70), ("Max ms", 70), ("Durée s", 65)]:
            self._runs_tree.column(c, width=w, stretch=(c == "App"))
        sb_r.config(command=self._runs_tree.yview)
        self._runs_tree.pack(fill="both", expand=True)
        for tag, fg in [("ok", _GREEN), ("warn", _YELLOW), ("error", _RED)]:
            self._runs_tree.tag_configure(tag, foreground=fg)

        # Treeview labels
        lbl_frame = ctk.CTkFrame(self._stats_tabs.tab("Stats par bouton"),
                                  fg_color=_BG3, corner_radius=6)
        lbl_frame.pack(fill="both", expand=True)
        lbl_cols = ("Cible", "App", "Type", "Exécutions",
                    "Avg ms", "Max ms", "Min ms", "Taux OK")
        sb_l = tk.Scrollbar(lbl_frame)
        sb_l.pack(side="right", fill="y")
        self._labels_tree = ttk.Treeview(lbl_frame, columns=lbl_cols,
                                          show="headings", style="V4.Treeview",
                                          yscrollcommand=sb_l.set)
        for c in lbl_cols:
            self._labels_tree.heading(c, text=c)
        for c, w in [("Cible", 200), ("App", 90), ("Type", 75),
                     ("Exécutions", 80), ("Avg ms", 70),
                     ("Max ms", 70), ("Min ms", 70), ("Taux OK", 70)]:
            self._labels_tree.column(c, width=w, stretch=(c == "Cible"))
        sb_l.config(command=self._labels_tree.yview)
        self._labels_tree.pack(fill="both", expand=True)
        for tag, fg in [("ok", _GREEN), ("warn", _YELLOW), ("error", _RED)]:
            self._labels_tree.tag_configure(tag, foreground=fg)

        self._stats_info_lbl = ctk.CTkLabel(parent, text="",
                                              font=_FONT_SM, text_color=_FG2,
                                              anchor="w")
        self._stats_info_lbl.pack(fill="x", padx=8, pady=(4, 0))

        self.after(800, self._load_stats_sessions)

    # ── Moniteurs ──────────────────────────────────────────────────────────────

    def _update_monitor_status(self):
        try:
            monitors = get_all_monitors()
            if len(monitors) == 1:
                m = monitors[0]
                txt = f"🖥  {m['width']}×{m['height']}"
            else:
                txt = f"🖥  {len(monitors)} écrans"
            self._monitor_var.set(txt)
        except Exception:
            pass

    # ── Liste des scénarios ───────────────────────────────────────────────────

    def _list_scenario_files(self) -> list[Path]:
        """Retourne tous les fichiers scénario/session JSON, triés par date desc."""
        files = []
        for d in (SCENARIOS_DIR_LOCAL, _LEGACY_SESSIONS_DIR):
            if d.exists():
                files.extend(d.glob("*.json"))
        return sorted(set(files), key=lambda p: p.stat().st_mtime, reverse=True)

    def _refresh_scenario_list(self):
        for row in self._scenario_rows:
            row.destroy()
        self._scenario_rows.clear()

        # Compter les runs par fichier (en DB)
        db_sessions = {s["filepath"]: s.get("run_count", 0)
                       for s in stats_db.get_all_sessions()}

        files = self._list_scenario_files()
        for path in files:
            run_count = db_sessions.get(str(path.resolve()), 0)
            row = _ScenarioRow(
                self._scen_scroll, path, run_count,
                on_select=self._on_scenario_select,
                on_delete=self._on_scenario_delete,
                on_rename=self._on_scenario_rename,
            )
            row.pack(fill="x", pady=2)
            self._scenario_rows.append(row)

    def _on_scenario_select(self, path: Path):
        for row in self._scenario_rows:
            row.set_selected(row.scenario_path == path)
        self._session_path = path
        self._replay_btn.configure(state="normal")
        name = self._read_scenario_display_name(path)
        self._status_var.set(f"Scénario : {name}")
        self._log_debug(f"✔ Scénario sélectionné : {name}", "info")
        # Pré-remplir l'application cible si le scénario en déclare une
        try:
            with open(path, encoding="utf-8") as f:
                tgt = json.load(f).get("target_app", "")
            if tgt:
                self._target_app_entry.delete(0, "end")
                self._target_app_entry.insert(0, tgt)
        except Exception:
            pass

    def _on_scenario_delete(self, path: Path):
        name = self._read_scenario_display_name(path)
        if not messagebox.askyesno("Supprimer",
                                    f"Supprimer définitivement le scénario :\n«{name}» ?",
                                    icon="warning"):
            return
        try:
            path.unlink()
        except Exception as e:
            messagebox.showerror("Erreur", str(e))
            return
        if self._session_path == path:
            self._session_path = None
            self._replay_btn.configure(state="disabled")
            self._status_var.set("Prêt")
        self._refresh_scenario_list()
        self._log_debug(f"🗑 Scénario supprimé : {name}", "warn")

    def _on_scenario_rename(self, path: Path, row: _ScenarioRow):
        current = self._read_scenario_display_name(path)
        dialog  = ctk.CTkInputDialog(
            title="Renommer le scénario",
            text=f"Nouveau nom pour «{current}» :",
        )
        new_name = dialog.get_input()
        if not new_name or new_name.strip() == current:
            return
        new_name = new_name.strip()
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            data["scenario_name"] = new_name
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            row.update_name(new_name)
            # Mettre à jour en DB
            stats_db.upsert_session(str(path.resolve()), new_name,
                                     data.get("action_count", 0))
            self._log_debug(f"✎ Renommé : {current!r} → {new_name!r}", "ok")
        except Exception as e:
            messagebox.showerror("Erreur", str(e))

    def _browse_scenario(self):
        path = filedialog.askopenfilename(
            title="Choisir un scénario",
            filetypes=[("JSON", "*.json"), ("Tous", "*.*")],
        )
        if path:
            self._session_path = Path(path)
            self._replay_btn.configure(state="normal")
            name = self._read_scenario_display_name(self._session_path)
            self._status_var.set(f"Scénario : {name}")

    @staticmethod
    def _read_scenario_display_name(path: Path) -> str:
        try:
            with open(path, encoding="utf-8") as f:
                d = json.load(f)
            return d.get("scenario_name") or path.stem
        except Exception:
            return path.stem

    # ── Enregistrement ────────────────────────────────────────────────────────

    def _toggle_record(self):
        if self._recorder is None:
            name = self._scenario_name_entry.get().strip() or ""
            target_app = self._target_app_entry.get().strip()
            self._recorder = ActionRecorder(scenario_name=name, target_app=target_app,
                                             reader=self._ocr_reader)
            self._recorder.start()
            self._rec_btn.configure(text="  ■  STOP RECORD",
                                     fg_color=_RED, hover_color="#B04050")
            self._replay_btn.configure(state="disabled")
            self._status_var.set("⬤ Enregistrement…")
            self._log_debug("⬤ Enregistrement démarré.", "heading")
            self._log_official(f"REC  Enregistrement «{name or '(sans nom)'}» démarré", "head")
        else:
            path = self._recorder.stop()
            self._recorder = None
            self._rec_btn.configure(text="  ⬤  RECORD",
                                     fg_color=_GREEN, hover_color="#35A07E")
            name = self._read_scenario_display_name(path)
            self._log_debug(f"■ Scénario sauvegardé : {path.name}", "ok")
            self._log_official(f"■  Scénario enregistré : {name}", "ok")
            self._status_var.set(f"Enregistré : {name}")
            self._refresh_scenario_list()
            self._replay_btn.configure(state="normal")

    # ── Replay ────────────────────────────────────────────────────────────────

    def _start_replay(self):
        if not self._session_path or not self._session_path.exists():
            messagebox.showwarning("Scénario introuvable",
                                   "Sélectionnez d'abord un scénario.")
            return

        n_runs   = max(1, self._spin_runs.get())
        interval = max(0.0, self._interval_var.get())

        self._results.clear()
        self._report_json_path = self._report_html_path = None
        self._clear_tree()
        self._replay_btn.configure(state="disabled")
        self._stop_btn.configure(state="normal")
        self._progress_bar.set(0)
        self._current_run_index  = 0
        self._total_runs_planned = n_runs

        scenario_name = self._read_scenario_display_name(self._session_path)
        self._run_lbl.configure(text=f"Run 1/{n_runs}" if n_runs > 1 else "")
        self._status_var.set("Replay en cours…")
        self._tabs.set("Journal")
        self._log_tabs.set("Journal officiel")

        self._log_debug(
            f"▶ Replay × {n_runs} — scénario : {scenario_name}", "heading")
        if n_runs > 1:
            self._log_debug(f"  Intervalle : {interval}s", "info")

        if n_runs == 1:
            self._replayer = ActionReplayer(
                ocr_similarity_min=self._ocr_threshold_var.get(),
                on_progress=self._on_action_progress,
                reader=self._ocr_reader,
            )
            session = self._replayer.load_session(self._session_path)
            self._total_actions = len(session.get("actions", []))
            self._replay_thread = threading.Thread(
                target=self._run_single, args=(session,), daemon=True)
        else:
            self._multi_runner = MultiReplayRunner(
                ocr_similarity_min=self._ocr_threshold_var.get(),
                on_run_start=self._on_multi_run_start,
                on_run_done=self._on_multi_run_done,
                on_progress=self._on_action_progress,
            )
            with open(self._session_path, encoding="utf-8") as f:
                _s = json.load(f)
            self._total_actions = len(_s.get("actions", []))
            self._replay_thread = threading.Thread(
                target=self._run_multi, args=(n_runs, interval), daemon=True)

        self._replay_thread.start()

    def _run_single(self, session: dict):
        try:
            results    = self._replayer.replay(session)
            self._results = results
            json_path  = self._replayer.save_report(self._session_path)
            html_path  = Path(str(json_path).replace(".json", ".html"))
            self._replayer.save_to_db(self._session_path)
            self.after(0, self._on_replay_done, results, json_path, html_path)
        except Exception as e:
            self.after(0, self._log_debug, f"ERREUR replay : {e}", "error")
            self.after(0, self._on_replay_finished)

    def _run_multi(self, n_runs: int, interval: float):
        try:
            all_res = self._multi_runner.run_n_times(
                self._session_path, n=n_runs, interval_s=interval, save_to_db=True)
            last = all_res[-1] if all_res else []
            self._results = last
            json_path = html_path = None
            if last:
                rep = ActionReplayer()
                rep._results = last
                json_path = rep.save_report(self._session_path)
                html_path = Path(str(json_path).replace(".json", ".html"))
            self.after(0, self._on_multi_all_done, all_res, json_path, html_path)
        except Exception as e:
            self.after(0, self._log_debug, f"ERREUR multi-run : {e}", "error")
            self.after(0, self._on_replay_finished)

    def _stop_replay(self):
        if self._replayer:
            self._replayer.stop()
        if self._multi_runner:
            self._multi_runner.stop()
        self._log_debug("■ Replay interrompu.", "warn")

    def _on_multi_run_start(self, idx: int, total: int):
        self._current_run_index = idx
        self.after(0, self._run_lbl.configure, {"text": f"Run {idx}/{total}"})
        self.after(0, self._log_debug, f"═══ Run {idx}/{total} ═══", "run")
        self.after(0, self._progress_bar.set, 0)
        self.after(0, self._clear_tree)

    def _on_multi_run_done(self, idx: int, total: int, results: list[ActionResult]):
        ok    = sum(1 for r in results if r.status == "ok")
        times = [r.response_time_ms for r in results if r.response_time_ms]
        avg   = f"{sum(times)/len(times):.0f}ms" if times else "—"
        self.after(0, self._log_debug,
                   f"✔ Run {idx}/{total} — OK:{ok}/{len(results)} avg:{avg}", "ok")
        self.after(0, self._update_report_summary, results)
        self.after(0, self._refresh_stats_silent)

    def _on_action_progress(self, current: int, total: int, result: ActionResult):
        self.after(0, self._update_progress, current, total, result)

    def _update_progress(self, current: int, total: int, result: ActionResult):
        pct = (current / total) if total > 0 else 0
        self._progress_bar.set(pct)
        self._progress_lbl.configure(text=f"{current}/{total}")

        label = result.label or ""
        if result.skipped:
            tag, status = "warn", f"IGNORÉ — {result.error or ''}"
        elif result.error:
            tag, status = "error", f"ERREUR — {result.error}"
        else:
            rt = f"{result.response_time_ms:.0f}ms" if result.response_time_ms else "—"
            tag, status = "ok", f"OK  ⏱ {rt}"

        label_part = f"  [{label}]" if label else ""
        self._log_debug(
            f"[{result.index:>3}] {result.action_type:<14}{label_part:<22}  {status}", tag)
        self._add_tree_row(result)

    def _on_replay_done(self, results: list[ActionResult],
                        json_path: Path, html_path: Path):
        self._report_json_path = json_path
        self._report_html_path = html_path if html_path and html_path.exists() else None
        self._on_replay_finished()

        scenario_name = self._read_scenario_display_name(self._session_path)
        self._log_debug(f"✔ Replay terminé. JSON : {json_path.name}", "ok")
        self._status_var.set("Replay terminé.")
        self._tabs.set("Rapport")
        self._update_report_summary(results)
        self._load_official_log()
        self._load_stats_sessions()
        self.after(200, self._refresh_stats_silent)
        if any(r.status == "error" for r in results):
            self._show_failure_popup(scenario_name, results)

    def _on_multi_all_done(self, all_res, json_path, html_path):
        n = len(all_res)
        self._log_debug(f"✔ {n} run(s) terminés — persistés en DB.", "run")
        if json_path:
            self._report_json_path = json_path
            self._report_html_path = html_path if html_path and html_path.exists() else None
        self._on_replay_finished()
        self._status_var.set(f"{n} run(s) terminé(s).")
        self._load_official_log()
        self._load_stats_sessions()
        self.after(200, lambda: (self._tabs.set("Stats long-terme"),
                                  self._refresh_stats_silent()))
        # Alerte si au moins un run du lot a échoué
        failing = next((run for run in all_res
                        if any(r.status == "error" for r in run)), None)
        if failing is not None:
            scen = (self._read_scenario_display_name(self._session_path)
                    if self._session_path else "?")
            self._show_failure_popup(scen, failing)

    def _on_replay_finished(self):
        self._replay_btn.configure(state="normal")
        self._stop_btn.configure(state="disabled")
        self._progress_bar.set(1)
        self._run_lbl.configure(text="")

    # ── Rapport ───────────────────────────────────────────────────────────────

    def _add_tree_row(self, r: ActionResult):
        ocr  = f"{r.ocr_match:.2f}" if r.ocr_match is not None else "—"
        vis  = "✔" if r.visual_ok else ("✘" if r.visual_ok is False else "—")
        resp = f"{r.response_time_ms:.0f}" if r.response_time_ms is not None else "—"
        tag, status = (("warn", "IGNORÉ") if r.skipped
                       else (("error", r.error[:40]) if r.error else ("ok", "OK")))
        iid = self._tree.insert("", "end",
                                 values=(r.index, r.action_type,
                                         r.label or "—", ocr, vis, resp, status))
        self._tree.item(iid, tags=(tag,))

    def _clear_tree(self):
        for item in self._tree.get_children():
            self._tree.delete(item)
        self._report_summary_lbl.configure(text="")

    def _update_report_summary(self, results: list[ActionResult]):
        total = len(results)
        ok    = sum(1 for r in results if r.status == "ok")
        skip  = sum(1 for r in results if r.status == "skip")
        errs  = sum(1 for r in results if r.status == "error")
        times = [r.response_time_ms for r in results if r.response_time_ms]
        avg_t = f"{sum(times)/len(times):.0f}ms" if times else "—"
        max_t = f"{max(times):.0f}ms" if times else "—"
        self._report_summary_lbl.configure(
            text=f"Total {total}  ✔{ok}  ⚠{skip}  ✘{errs}   ⏱ avg {avg_t}  max {max_t}")

    def _export_report_json(self):
        if not self._results:
            messagebox.showinfo("Rapport vide", "Aucun résultat disponible.")
            return
        path = filedialog.asksaveasfilename(
            title="Exporter JSON", initialdir=REPORTS_DIR,
            defaultextension=".json", filetypes=[("JSON", "*.json")])
        if path:
            with open(path, "w", encoding="utf-8") as f:
                json.dump([r.to_dict() for r in self._results],
                          f, ensure_ascii=False, indent=2)
            self._log_debug(f"Rapport JSON → {path}", "ok")

    def _export_report_html(self):
        if not self._results:
            messagebox.showinfo("Rapport vide", "Aucun résultat disponible.")
            return
        if self._report_html_path and self._report_html_path.exists():
            if messagebox.askyesno("HTML existant",
                                    f"Ouvrir {self._report_html_path.name} ?"):
                webbrowser.open(self._report_html_path.as_uri())
                return
        path = filedialog.asksaveasfilename(
            title="Exporter HTML", initialdir=REPORTS_DIR,
            defaultextension=".html", filetypes=[("HTML", "*.html")])
        if not path:
            return
        rep = ActionReplayer()
        rep._results = self._results
        ts   = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        stem = (self._session_path.stem if self._session_path else "scenario")
        html = rep._build_html_report(
            rep._build_report_dict(self._session_path or Path("scenario.json"), ts),
            stem, ts)
        Path(path).write_text(html, encoding="utf-8")
        self._log_debug(f"Rapport HTML → {path}", "ok")
        webbrowser.open(Path(path).as_uri())

    # ── Journal officiel ──────────────────────────────────────────────────────

    def _load_official_log(self):
        """Recharge les entrées du journal officiel dans la textbox."""
        try:
            entries = official_log.get_recent_entries(200)
            self._official_log_box.configure(state="normal")
            self._official_log_box.delete("0.0", "end")
            for e in entries:
                status = e.get("status", "")
                tag = ("ok" if status == "SUCCÈS"
                       else ("warn" if status == "PARTIEL" else "err"))
                icon = "✔" if status == "SUCCÈS" else ("⚠" if status == "PARTIEL" else "✘")
                ok_t = e.get("ok_count", "?")
                tot  = e.get("total_count", "?")
                dur  = e.get("duration_s", "?")
                line = (f"[{e.get('execution_date','')[:19]}] "
                        f"{icon} {status:<8}  "
                        f"{e.get('app_name','—'):<16}  "
                        f"{e.get('scenario_name','—'):<24}  "
                        f"{ok_t}/{tot} actions  "
                        f"⏱ {dur}s\n")
                self._official_log_box._textbox.configure(state="normal")
                self._official_log_box._textbox.insert("end", line, tag)
                self._official_log_box._textbox.configure(state="disabled")
            self._official_log_box.configure(state="disabled")
        except Exception:
            pass

    def _export_official_csv(self):
        paths = official_log.get_all_log_paths()
        if not paths:
            messagebox.showinfo("Aucun log", "Aucun journal officiel disponible.")
            return
        # Propose le fichier le plus récent
        dst = filedialog.asksaveasfilename(
            title="Exporter le journal officiel",
            initialdir=Path("logs"),
            initialfile=paths[0].name,
            defaultextension=".csv",
            filetypes=[("CSV", "*.csv"), ("Tous", "*.*")],
        )
        if dst:
            import shutil
            shutil.copy2(paths[0], dst)
            self._log_debug(f"Journal officiel exporté → {dst}", "ok")

    # ── Stats long-terme ──────────────────────────────────────────────────────

    def _on_tab_changed(self):
        try:
            if self._tabs.get() == "Stats long-terme":
                self._refresh_stats_silent()
        except Exception:
            pass

    def _load_stats_sessions(self):
        """Charge la liste des sessions de la DB dans le combobox."""
        try:
            sessions = stats_db.get_all_sessions()
            self._stats_sessions_data = sessions
            values = []
            for s in sessions:
                sname = s.get("scenario_name") or s.get("name") or "—"
                values.append(f"{sname}  (id={s['id']}, {s.get('run_count',0)} runs)")
            self._stats_session_cb.configure(values=values)
            if values and not self._stats_session_var.get():
                self._stats_session_cb.set(values[0])
                self._refresh_stats_silent()
            elif values:
                # Réactualise la sélection courante sans reset
                self._refresh_stats_silent()
        except Exception as e:
            self._log_debug(f"[stats] Erreur chargement sessions : {e}", "error")

    def _refresh_stats_full(self):
        """Recharge sessions ET rafraîchit l'affichage."""
        self._load_stats_sessions()

    def _refresh_stats_silent(self):
        """Rafraîchit l'affichage sans modifier le combobox."""
        try:
            if not hasattr(self, "_stats_sessions_data"):
                self._load_stats_sessions()
                return
            sessions = self._stats_sessions_data
            if not sessions:
                return
            # Trouver l'index sélectionné
            cur_val = self._stats_session_var.get()
            idx = 0
            for i, s in enumerate(sessions):
                sname = s.get("scenario_name") or s.get("name") or "—"
                if sname in cur_val or str(s["id"]) in cur_val:
                    idx = i
                    break
            self._refresh_stats_for_index(idx)
        except Exception as e:
            self._log_debug(f"[stats] Erreur refresh : {e}", "error")

    def _refresh_stats(self):
        """Appelé par le combobox."""
        try:
            sessions = getattr(self, "_stats_sessions_data", [])
            if not sessions:
                self._load_stats_sessions()
                return
            cur_val = self._stats_session_var.get()
            idx = 0
            for i, s in enumerate(sessions):
                sname = s.get("scenario_name") or s.get("name") or "—"
                if sname in cur_val or str(s["id"]) in cur_val:
                    idx = i
                    break
            self._refresh_stats_for_index(idx)
        except Exception as e:
            self._log_debug(f"[stats] Erreur : {e}", "error")

    def _refresh_stats_for_index(self, idx: int):
        sessions = getattr(self, "_stats_sessions_data", [])
        if idx >= len(sessions):
            return
        sid = sessions[idx]["id"]

        # Runs
        for item in self._runs_tree.get_children():
            self._runs_tree.delete(item)
        try:
            runs = stats_db.get_session_runs(sid)
            for r in runs:
                pct = (r["ok_count"] * 100 // r["total"]) if r.get("total") else 0
                tag = "ok" if pct == 100 else ("warn" if pct >= 70 else "error")
                avg = f"{r['avg_response_ms']:.0f}" if r.get("avg_response_ms") else "—"
                mx  = f"{r['max_response_ms']:.0f}" if r.get("max_response_ms") else "—"
                dur = f"{r['total_duration_s']:.1f}" if r.get("total_duration_s") else "—"
                # Récupérer app_name depuis les résultats du run
                actions = stats_db.get_run_actions(r["id"])
                app = next((a["app_name"] for a in actions if a.get("app_name")), "—")
                iid = self._runs_tree.insert("", "end", values=(
                    f"#{r['run_number']}",
                    (r["started_at"] or "").replace("T", " ")[:19],
                    app,
                    r.get("total", "—"),
                    r["ok_count"], r["skip_count"], r["error_count"],
                    avg, mx, dur,
                ))
                self._runs_tree.item(iid, tags=(tag,))
        except Exception as e:
            self._log_debug(f"[stats/runs] {e}", "error")

        # Labels
        for item in self._labels_tree.get_children():
            self._labels_tree.delete(item)
        try:
            label_stats = stats_db.get_label_stats(sid)
            for l in label_stats:
                sr  = l.get("success_rate") or 0
                tag = "ok" if sr >= 95 else ("warn" if sr >= 70 else "error")
                avg = f"{l['avg_ms']:.0f}" if l.get("avg_ms") else "—"
                mx  = f"{l['max_ms']:.0f}" if l.get("max_ms") else "—"
                mn  = f"{l['min_ms']:.0f}" if l.get("min_ms") else "—"
                iid = self._labels_tree.insert("", "end", values=(
                    l.get("label") or "—",
                    l.get("app_name") or "—",
                    l.get("action_type") or "—",
                    l.get("run_count", "—"),
                    avg, mx, mn,
                    f"{sr:.1f}%",
                ))
                self._labels_tree.item(iid, tags=(tag,))
        except Exception as e:
            self._log_debug(f"[stats/labels] {e}", "error")

        s = sessions[idx]
        sname = s.get("scenario_name") or s.get("name") or "—"
        self._stats_info_lbl.configure(
            text=f"{sname} — {s.get('run_count',0)} run(s) — "
                 f"{s.get('action_count',0)} actions")

    def _export_csv(self):
        sessions = getattr(self, "_stats_sessions_data", [])
        if not sessions:
            messagebox.showinfo("Aucune session", "Sélectionnez un scénario.")
            return
        cur_val = self._stats_session_var.get()
        idx, sid, sname = 0, sessions[0]["id"], "export"
        for i, s in enumerate(sessions):
            n = s.get("scenario_name") or s.get("name") or "—"
            if n in cur_val or str(s["id"]) in cur_val:
                idx, sid, sname = i, s["id"], n
                break
        path = filedialog.asksaveasfilename(
            title="Exporter CSV", initialdir=REPORTS_DIR,
            defaultextension=".csv",
            initialfile=f"{sname}_export.csv",
            filetypes=[("CSV", "*.csv"), ("Tous", "*.*")],
        )
        if not path:
            return
        try:
            csv_data = stats_db.export_csv(sid)
            Path(path).write_text(csv_data, encoding="utf-8-sig")
            self._log_debug(f"CSV exporté → {path}", "ok")
        except Exception as e:
            messagebox.showerror("Erreur CSV", str(e))

    # ── Dashboard web ─────────────────────────────────────────────────────────

    def _open_dashboard(self):
        global _SERVER_PROC, _SERVER_PORT
        url = f"http://127.0.0.1:{_SERVER_PORT}/"
        if _SERVER_PROC is None or _SERVER_PROC.poll() is not None:
            try:
                _SERVER_PROC = subprocess.Popen(
                    [sys.executable, "report_server.py", f"--port={_SERVER_PORT}"],
                    cwd=Path(__file__).parent,
                )
                self._log_debug(f"🌐 Dashboard lancé → {url}", "heading")
                self.after(1500, lambda: webbrowser.open(url))
            except Exception as e:
                messagebox.showerror("Dashboard", str(e))
        else:
            self._log_debug(f"🌐 Dashboard actif → {url}", "info")
            webbrowser.open(url)

    # ── Mode automatique (daemon + systray) ──────────────────────────────────

    def _toggle_auto(self):
        if self._auto_running:
            self._stop_auto()
        else:
            self._start_auto()

    def _start_auto(self):
        if not self._session_path or not self._session_path.exists():
            messagebox.showwarning("Scénario introuvable",
                                   "Sélectionnez d'abord un scénario à automatiser.")
            return
        if self._recorder is not None:
            messagebox.showwarning("Enregistrement en cours",
                                   "Arrêtez l'enregistrement avant de lancer le mode automatique.")
            return
        try:
            interval_min = max(0.1, float(self._auto_interval_var.get()))
        except Exception:
            interval_min = 30.0
            self._auto_interval_var.set(30.0)

        scenario_name = self._read_scenario_display_name(self._session_path)
        self._scheduler = SchedulerRunner(
            ocr_similarity_min=self._ocr_threshold_var.get(),
            on_cycle_start=self._on_auto_cycle_start,
            on_cycle_done=self._on_auto_cycle_done,
            on_progress=self._on_action_progress,
            on_wait=self._on_auto_wait,
        )
        self._auto_running = True
        self._auto_btn.configure(text="  ■  Arrêter l'automatique",
                                 fg_color=_RED, hover_color="#B04050")
        self._replay_btn.configure(state="disabled")
        self._rec_btn.configure(state="disabled")
        self._status_var.set("🔁 Mode automatique actif")
        self._tabs.set("Journal")
        self._log_official(
            f"🔁 Mode automatique démarré — «{scenario_name}» toutes les "
            f"{interval_min:.0f} min", "head")
        self._log_debug(
            f"🔁 Mode automatique : {scenario_name} / cycle {interval_min:.0f} min",
            "heading")

        self._auto_thread = threading.Thread(
            target=self._scheduler.run_forever,
            kwargs={"session_path": self._session_path,
                    "interval_minutes": interval_min},
            daemon=True,
        )
        self._auto_thread.start()
        # Réduire dans la zone de notification après le démarrage
        self.after(500, self._hide_to_tray)

    def _stop_auto(self):
        if self._scheduler:
            self._scheduler.stop()
        self._auto_running = False
        self._auto_btn.configure(text="  ⏱  Démarrer l'automatique",
                                 fg_color=_ACCENT2, hover_color="#C9733F")
        self._replay_btn.configure(
            state="normal" if self._session_path else "disabled")
        self._rec_btn.configure(state="normal")
        self._auto_status_lbl.configure(text="")
        self._status_var.set("Mode automatique arrêté.")
        self._log_official("■ Mode automatique arrêté", "warn")
        self._log_debug("■ Mode automatique arrêté.", "warn")
        self._remove_tray()

    # callbacks scheduler (appelés depuis le thread daemon → marshalés via after)

    def _on_auto_cycle_start(self, cycle: int):
        self.after(0, self._auto_cycle_start_ui, cycle)

    def _auto_cycle_start_ui(self, cycle: int):
        self._run_lbl.configure(text=f"Auto #{cycle}")
        self._progress_bar.set(0)
        self._clear_tree()
        self._log_debug(f"═══ Cycle automatique #{cycle} ═══", "run")

    def _on_auto_cycle_done(self, cycle: int, results, status: str, run_id: int):
        self.after(0, self._auto_cycle_done_ui, cycle, results, status, run_id)

    def _auto_cycle_done_ui(self, cycle: int, results, status: str, run_id: int):
        ok    = sum(1 for r in results if getattr(r, "status", "") == "ok")
        total = len(results)
        tag = ("ok" if status == official_log.STATUS_SUCCESS
               else ("warn" if status == official_log.STATUS_PARTIAL else "error"))
        self._results = results
        self._log_debug(f"✔ Cycle #{cycle} — {status} — OK {ok}/{total}", tag)
        self._update_report_summary(results)
        self._load_official_log()
        self._load_stats_sessions()
        self._refresh_stats_silent()
        if status == official_log.STATUS_FAILURE:
            name = (self._read_scenario_display_name(self._session_path)
                    if self._session_path else "?")
            self._show_failure_popup(name, results, cycle=cycle)

    def _on_auto_wait(self, cycle: int, next_run_epoch: float):
        nxt = datetime.datetime.fromtimestamp(next_run_epoch).strftime("%H:%M:%S")
        self.after(0, self._auto_status_lbl.configure,
                   {"text": f"Cycle #{cycle} terminé · prochain à {nxt}"})

    # systray

    def _make_tray_image(self):
        img = _PILImage.new("RGB", (64, 64), _BG2)
        d = _PILDraw.Draw(img)
        d.ellipse((8, 8, 56, 56), fill=_ACCENT)
        d.ellipse((22, 24, 31, 33), fill=_BG)
        d.ellipse((38, 24, 47, 33), fill=_BG)
        d.rectangle((24, 42, 44, 46), fill=_BG)
        return img

    def _hide_to_tray(self):
        if not self._auto_running:
            return
        if _HAS_TRAY and self._tray_icon is None:
            try:
                self._setup_tray()
                self.withdraw()
                return
            except Exception as e:
                self._log_debug(f"Systray indisponible : {e}", "warn")
        # Repli : réduction classique dans la barre des tâches
        self.iconify()

    def _setup_tray(self):
        menu = pystray.Menu(
            pystray.MenuItem("Ouvrir WinGhost", self._tray_restore, default=True),
            pystray.MenuItem("Arrêter l'automatique", self._tray_stop_auto),
            pystray.MenuItem("Quitter", self._tray_quit),
        )
        self._tray_icon = pystray.Icon(
            "winghost", self._make_tray_image(),
            "WinGhost RPA — mode automatique", menu)
        threading.Thread(target=self._tray_icon.run, daemon=True).start()

    def _tray_restore(self, icon=None, item=None):
        self.after(0, self._restore_from_tray)

    def _restore_from_tray(self):
        try:
            self.deiconify()
            self.lift()
            self.focus_force()
        except Exception:
            pass

    def _tray_stop_auto(self, icon=None, item=None):
        self.after(0, self._stop_auto)

    def _tray_quit(self, icon=None, item=None):
        self.after(0, self._on_close)

    def _remove_tray(self):
        if self._tray_icon is not None:
            try:
                self._tray_icon.stop()
            except Exception:
                pass
            self._tray_icon = None
        try:
            self.deiconify()
        except Exception:
            pass

    # alerte d'échec

    def _show_failure_popup(self, scenario_name: str, results=None, cycle=None):
        # Toujours rendre la fenêtre visible avant d'alerter
        self._restore_from_tray()

        errors = [r for r in (results or []) if getattr(r, "status", "") == "error"]
        lines = []
        for r in errors[:6]:
            lbl = getattr(r, "label", "") or getattr(r, "action_type", "")
            lines.append(f"#{getattr(r, 'index', '?')}  {lbl} — {getattr(r, 'error', '') or ''}")
        if len(errors) > 6:
            lines.append(f"… et {len(errors) - 6} autre(s) erreur(s)")
        detail = "\n".join(lines) or "Une ou plusieurs actions ont échoué pendant l'exécution."

        cyc = f"  ·  cycle #{cycle}" if cycle is not None else ""

        try:
            self.bell()
        except Exception:
            pass

        pop = ctk.CTkToplevel(self)
        pop.title("ÉCHEC — WinGhost RPA")
        pop.configure(fg_color=_RED)
        pw, ph = 640, 380
        try:
            sx = self.winfo_rootx() + (self.winfo_width() - pw) // 2
            sy = self.winfo_rooty() + (self.winfo_height() - ph) // 2
            pop.geometry(f"{pw}x{ph}+{max(sx,0)}+{max(sy,0)}")
        except Exception:
            pop.geometry(f"{pw}x{ph}")
        pop.attributes("-topmost", True)
        pop.lift()
        try:
            pop.grab_set()
        except Exception:
            pass

        inner = ctk.CTkFrame(pop, fg_color=_BG2, corner_radius=14)
        inner.pack(fill="both", expand=True, padx=6, pady=6)

        ctk.CTkLabel(inner, text="✘", font=("Segoe UI", 72, "bold"),
                     text_color=_RED).pack(pady=(18, 0))
        ctk.CTkLabel(inner, text="ÉCHEC D'EXÉCUTION",
                     font=("Segoe UI Semibold", 22), text_color=_RED).pack()
        ctk.CTkLabel(inner, text=f"Scénario : {scenario_name}{cyc}",
                     font=("Segoe UI", 13), text_color=_FG).pack(pady=(6, 10))

        box = ctk.CTkTextbox(inner, font=_FONT_MONO, fg_color=_BG3,
                             text_color=_YELLOW, height=110, corner_radius=8)
        box.pack(fill="x", expand=False, padx=24)
        box.insert("0.0", detail)
        box.configure(state="disabled")

        ctk.CTkButton(inner, text="  J'ai compris  ",
                      font=("Segoe UI Semibold", 14),
                      fg_color=_RED, hover_color="#B04050", text_color=_BG,
                      height=42, corner_radius=10,
                      command=pop.destroy).pack(pady=16)

        self._log_debug(f"⚠ ALERTE ÉCHEC — {scenario_name}{cyc}", "error")

    # ── Journaux ──────────────────────────────────────────────────────────────

    def _log_debug(self, message: str, tag: str = "info"):
        ts   = datetime.datetime.now().strftime("%H:%M:%S")
        line = f"[{ts}] {message}\n"
        try:
            box = self._debug_log_box._textbox
            box.configure(state="normal")
            box.insert("end", line, tag)
            box.see("end")
            box.configure(state="disabled")
        except Exception:
            pass

    def _log_official(self, message: str, tag: str = "head"):
        ts   = datetime.datetime.now().strftime("%H:%M:%S")
        line = f"[{ts}] {message}\n"
        try:
            box = self._official_log_box._textbox
            box.configure(state="normal")
            box.insert("end", line, tag)
            box.see("end")
            box.configure(state="disabled")
        except Exception:
            pass

    # ── Utilitaires ───────────────────────────────────────────────────────────

    @staticmethod
    def _open_folder(path: Path):
        if sys.platform == "win32":
            os.startfile(str(path))
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(path)])
        else:
            subprocess.Popen(["xdg-open", str(path)])

    def _on_close(self):
        global _SERVER_PROC
        if self._scheduler:
            self._scheduler.stop()
        self._remove_tray()
        if _SERVER_PROC and _SERVER_PROC.poll() is None:
            _SERVER_PROC.terminate()
        self.destroy()


# ─── Lancement ────────────────────────────────────────────────────────────────

def main():
    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()
