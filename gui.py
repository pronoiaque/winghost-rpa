"""
gui.py — Interface Tkinter pour enregistrer et rejouer des sessions.

v3 :
  • Multi-run : spinner « Répétitions » (1–99) + champ « Intervalle (s) »
  • Capture de screenshots post-action (option replay)
  • Onglet « Stats long-terme » : historique des runs depuis la DB
  • Bouton « 🌐 Dashboard Web » (ouvre report_server.py dans un subprocess)
  • Export CSV direct depuis l'onglet Stats

v2 (conservé) :
  • Bouton RECORD / STOP, liste de sessions, seuil OCR
  • Journal temps réel coloré, onglet Rapport avec Treeview
  • Export JSON / HTML avec graphique SVG, support multi-moniteurs
"""

import datetime
import json
import subprocess
import sys
import threading
import webbrowser
from pathlib import Path

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

try:
    from recorder import ActionRecorder, get_all_monitors
    from replayer import (ActionReplayer, ActionResult, MultiReplayRunner,
                          SESSIONS_DIR, REPORTS_DIR)
    import stats_db
except ImportError as e:
    import tkinter.messagebox as _mb
    _mb.showerror("Import manquant", str(e))
    sys.exit(1)

# ─── Palette ──────────────────────────────────────────────────────────────────

BG        = "#1C1F26"
BG2       = "#252932"
BG3       = "#2E3440"
BG4       = "#353B4A"
ACCENT    = "#5E9BF0"
ACCENT2   = "#F0965E"
GREEN     = "#4EC9A0"
RED       = "#E06C75"
YELLOW    = "#E5C07B"
FG        = "#D8DEE9"
FG2       = "#7B8496"
FONT_MONO = ("Consolas", 9)
FONT_UI   = ("Segoe UI", 10)
FONT_H1   = ("Segoe UI Semibold", 13)

_SERVER_PORT  = 5000
_SERVER_PROC  = None   # subprocess du dashboard web


# ─── Utilitaires ──────────────────────────────────────────────────────────────

def center_window_on_primary(win: tk.Tk, w: int = 980, h: int = 700):
    monitors = get_all_monitors()
    m = monitors[0]
    x = m["left"] + (m["width"]  - w) // 2
    y = m["top"]  + (m["height"] - h) // 2
    win.geometry(f"{w}x{h}+{x}+{y}")


def monitor_summary() -> str:
    monitors = get_all_monitors()
    if len(monitors) == 1:
        m = monitors[0]
        return f"1 écran  {m['width']}×{m['height']}"
    return f"{len(monitors)} écrans  " + "  +  ".join(f"{m['width']}×{m['height']}" for m in monitors)


# ─── Application principale ───────────────────────────────────────────────────

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("WinGhost RPA v3")
        self.configure(bg=BG)
        self.resizable(True, True)
        self.minsize(920, 680)
        center_window_on_primary(self)

        self._recorder: ActionRecorder | None = None
        self._replayer: ActionReplayer | None = None
        self._multi_runner: MultiReplayRunner | None = None
        self._session_path: Path | None = None
        self._replay_thread: threading.Thread | None = None
        self._results: list[ActionResult] = []
        self._report_json_path: Path | None = None
        self._report_html_path: Path | None = None
        self._current_run_index  = 0
        self._total_runs_planned = 1

        stats_db.init_db()
        self._build_ui()
        self._refresh_session_list()
        self.after(200, self._update_monitor_status)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ── Construction UI ───────────────────────────────────────────────────────

    def _build_ui(self):
        # Header
        header = tk.Frame(self, bg=BG, pady=10)
        header.pack(fill="x", padx=20)
        tk.Label(header, text="WinGhost RPA v3", font=FONT_H1, bg=BG, fg=FG).pack(side="left")
        self._status_var = tk.StringVar(value="Prêt")
        tk.Label(header, textvariable=self._status_var,
                 font=FONT_UI, bg=BG, fg=FG2).pack(side="right", padx=10)
        self._monitor_var = tk.StringVar(value="")
        tk.Label(header, textvariable=self._monitor_var,
                 font=("Segoe UI", 9), bg=BG, fg=FG2).pack(side="right", padx=(0, 16))

        tk.Frame(self, bg=BG3, height=1).pack(fill="x", padx=20)

        main = tk.Frame(self, bg=BG)
        main.pack(fill="both", expand=True, padx=20, pady=10)

        left = tk.Frame(main, bg=BG, width=290)
        left.pack(side="left", fill="y", padx=(0, 12))
        left.pack_propagate(False)

        right = tk.Frame(main, bg=BG)
        right.pack(side="left", fill="both", expand=True)

        self._build_left_panel(left)
        self._build_right_panel(right)

    def _build_left_panel(self, parent):
        # ── RECORD ───────────────────────────────────────────────────────────
        rec_frame = tk.LabelFrame(parent, text=" ⬤  Enregistrement ",
                                  font=FONT_UI, bg=BG2, fg=FG, bd=1,
                                  relief="flat", padx=10, pady=10)
        rec_frame.pack(fill="x", pady=(0, 10))

        self._screenshots_rec_var = tk.BooleanVar(value=False)
        tk.Checkbutton(rec_frame, text="Capturer screenshots (recorder)",
                       variable=self._screenshots_rec_var,
                       bg=BG2, fg=FG2, selectcolor=BG3,
                       activebackground=BG2, font=FONT_UI).pack(anchor="w")

        self._rec_btn = tk.Button(
            rec_frame, text="  ⬤  RECORD",
            command=self._toggle_record,
            bg=GREEN, fg=BG, font=("Segoe UI Semibold", 11),
            relief="flat", padx=12, pady=6, cursor="hand2",
        )
        self._rec_btn.pack(fill="x", pady=(8, 0))

        # ── Sessions ─────────────────────────────────────────────────────────
        sess_frame = tk.LabelFrame(parent, text=" ▶  Sessions ",
                                   font=FONT_UI, bg=BG2, fg=FG, bd=1,
                                   relief="flat", padx=10, pady=8)
        sess_frame.pack(fill="both", expand=True, pady=(0, 10))

        sb = tk.Scrollbar(sess_frame)
        sb.pack(side="right", fill="y")
        self._session_listbox = tk.Listbox(
            sess_frame, bg=BG3, fg=FG, font=FONT_MONO,
            selectbackground=ACCENT, selectforeground=BG,
            relief="flat", highlightthickness=0, yscrollcommand=sb.set,
        )
        self._session_listbox.pack(fill="both", expand=True)
        sb.config(command=self._session_listbox.yview)
        self._session_listbox.bind("<<ListboxSelect>>", self._on_session_select)

        btns = tk.Frame(sess_frame, bg=BG2)
        btns.pack(fill="x", pady=(6, 0))
        tk.Button(btns, text="Rafraîchir", command=self._refresh_session_list,
                  bg=BG3, fg=FG2, font=FONT_UI, relief="flat",
                  padx=6, pady=3, cursor="hand2").pack(side="left")
        tk.Button(btns, text="Parcourir…", command=self._browse_session,
                  bg=BG3, fg=FG2, font=FONT_UI, relief="flat",
                  padx=6, pady=3, cursor="hand2").pack(side="left", padx=(4, 0))

        # ── Options replay ────────────────────────────────────────────────────
        opt_frame = tk.LabelFrame(parent, text=" ⚙  Options replay ",
                                  font=FONT_UI, bg=BG2, fg=FG, bd=1,
                                  relief="flat", padx=10, pady=8)
        opt_frame.pack(fill="x", pady=(0, 10))
        opt_frame.columnconfigure(1, weight=1)

        # Seuil OCR
        tk.Label(opt_frame, text="Seuil OCR :", bg=BG2, fg=FG2,
                 font=FONT_UI).grid(row=0, column=0, sticky="w", pady=2)
        self._ocr_threshold_var = tk.DoubleVar(value=0.40)
        tk.Scale(opt_frame, variable=self._ocr_threshold_var, from_=0.0, to=1.0,
                 resolution=0.05, orient="horizontal", bg=BG2, fg=FG,
                 troughcolor=BG3, highlightthickness=0, sliderrelief="flat",
                 font=FONT_UI).grid(row=0, column=1, sticky="ew", padx=(6, 0))

        # Répétitions (multi-run)
        tk.Label(opt_frame, text="Répétitions :", bg=BG2, fg=FG2,
                 font=FONT_UI).grid(row=1, column=0, sticky="w", pady=2)
        self._n_runs_var = tk.IntVar(value=1)
        tk.Spinbox(opt_frame, textvariable=self._n_runs_var, from_=1, to=99,
                   bg=BG3, fg=FG, font=FONT_UI, relief="flat",
                   buttonbackground=BG4, width=6,
                   ).grid(row=1, column=1, sticky="w", padx=(6, 0))

        # Intervalle entre runs
        tk.Label(opt_frame, text="Intervalle (s) :", bg=BG2, fg=FG2,
                 font=FONT_UI).grid(row=2, column=0, sticky="w", pady=2)
        self._interval_var = tk.DoubleVar(value=5.0)
        tk.Entry(opt_frame, textvariable=self._interval_var,
                 bg=BG3, fg=FG, font=FONT_UI, relief="flat", width=7,
                 ).grid(row=2, column=1, sticky="w", padx=(6, 0))

        # Screenshots post-action
        self._screenshots_replay_var = tk.BooleanVar(value=False)
        tk.Checkbutton(opt_frame, text="Screenshots post-action",
                       variable=self._screenshots_replay_var,
                       bg=BG2, fg=FG2, selectcolor=BG3,
                       activebackground=BG2, font=FONT_UI,
                       ).grid(row=3, column=0, columnspan=2, sticky="w", pady=(4, 0))

        # ── Boutons REPLAY / STOP ─────────────────────────────────────────────
        action_frame = tk.Frame(parent, bg=BG)
        action_frame.pack(fill="x")

        self._replay_btn = tk.Button(
            action_frame, text="  ▶  REPLAY",
            command=self._start_replay,
            bg=ACCENT, fg=BG, font=("Segoe UI Semibold", 11),
            relief="flat", padx=12, pady=6, cursor="hand2",
            state="disabled",
        )
        self._replay_btn.pack(fill="x", pady=(0, 4))

        self._stop_btn = tk.Button(
            action_frame, text="  ■  STOP",
            command=self._stop_replay,
            bg=RED, fg=BG, font=("Segoe UI Semibold", 11),
            relief="flat", padx=12, pady=6, cursor="hand2",
            state="disabled",
        )
        self._stop_btn.pack(fill="x", pady=(0, 4))

        # Bouton Dashboard web
        self._dashboard_btn = tk.Button(
            action_frame, text="  🌐  Dashboard Web",
            command=self._open_dashboard,
            bg=BG3, fg=ACCENT, font=FONT_UI,
            relief="flat", padx=12, pady=5, cursor="hand2",
        )
        self._dashboard_btn.pack(fill="x")

    def _build_right_panel(self, parent):
        # Barre de progression
        prog_frame = tk.Frame(parent, bg=BG)
        prog_frame.pack(fill="x", pady=(0, 8))

        self._run_lbl = tk.Label(prog_frame, text="", font=FONT_UI, bg=BG, fg=ACCENT2)
        self._run_lbl.pack(side="left")

        self._progress_var = tk.DoubleVar(value=0)
        self._progress_lbl = tk.Label(prog_frame, text="0 / 0",
                                       font=FONT_UI, bg=BG, fg=FG2)
        self._progress_lbl.pack(side="right")

        style = ttk.Style()
        style.theme_use("clam")
        style.configure("RPA.Horizontal.TProgressbar",
                         troughcolor=BG3, background=ACCENT,
                         thickness=8, borderwidth=0)
        self._progress = ttk.Progressbar(
            prog_frame, variable=self._progress_var,
            style="RPA.Horizontal.TProgressbar",
            maximum=100,
        )
        self._progress.pack(fill="x", side="left", expand=True, padx=(8, 10))

        # Onglets
        nb_style = ttk.Style()
        nb_style.configure("RPA.TNotebook", background=BG, borderwidth=0)
        nb_style.configure("RPA.TNotebook.Tab", background=BG3, foreground=FG2,
                            padding=[12, 4], font=FONT_UI)
        nb_style.map("RPA.TNotebook.Tab",
                     background=[("selected", BG2)],
                     foreground=[("selected", FG)])

        self._notebook = ttk.Notebook(parent, style="RPA.TNotebook")
        self._notebook.pack(fill="both", expand=True)

        log_tab = tk.Frame(self._notebook, bg=BG2)
        self._notebook.add(log_tab, text="Journal")

        report_tab = tk.Frame(self._notebook, bg=BG2)
        self._notebook.add(report_tab, text="Rapport")

        stats_tab = tk.Frame(self._notebook, bg=BG2)
        self._notebook.add(stats_tab, text="Stats long-terme")

        self._build_log_tab(log_tab)
        self._build_report_tab(report_tab)
        self._build_stats_tab(stats_tab)

    def _build_log_tab(self, parent):
        self._log_text = tk.Text(
            parent, bg=BG2, fg=FG, font=FONT_MONO,
            relief="flat", highlightthickness=0,
            state="disabled", wrap="word",
        )
        sb = tk.Scrollbar(parent, command=self._log_text.yview)
        self._log_text.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self._log_text.pack(fill="both", expand=True, padx=2, pady=2)

        for tag, fg in [("ok", GREEN), ("warn", YELLOW), ("error", RED),
                        ("info", FG2), ("heading", ACCENT), ("label", ACCENT2),
                        ("run", ACCENT2)]:
            kw = {"foreground": fg}
            if tag in ("heading", "run"):
                kw["font"] = ("Consolas", 9, "bold")
            self._log_text.tag_configure(tag, **kw)

    def _build_report_tab(self, parent):
        cols = ("#", "Type", "Cible", "OCR Score", "Visuel OK", "Réponse (ms)", "Statut")
        tree_frame = tk.Frame(parent, bg=BG2)
        tree_frame.pack(fill="both", expand=True, padx=4, pady=4)

        sb = tk.Scrollbar(tree_frame)
        sb.pack(side="right", fill="y")

        ts = ttk.Style()
        ts.configure("RPA.Treeview", background=BG3, fieldbackground=BG3,
                     foreground=FG, rowheight=22, font=FONT_MONO, borderwidth=0)
        ts.configure("RPA.Treeview.Heading", background=BG2, foreground=ACCENT,
                     font=("Segoe UI Semibold", 9))
        ts.map("RPA.Treeview",
               background=[("selected", ACCENT)], foreground=[("selected", BG)])

        self._tree = ttk.Treeview(tree_frame, columns=cols, show="headings",
                                   style="RPA.Treeview", yscrollcommand=sb.set)
        for col in cols:
            self._tree.heading(col, text=col)
        self._tree.column("#",            width=40,  stretch=False)
        self._tree.column("Type",         width=100, stretch=False)
        self._tree.column("Cible",        width=180, stretch=True)
        self._tree.column("OCR Score",    width=75,  stretch=False)
        self._tree.column("Visuel OK",    width=70,  stretch=False)
        self._tree.column("Réponse (ms)", width=100, stretch=False)
        self._tree.column("Statut",       width=160, stretch=True)
        sb.config(command=self._tree.yview)
        self._tree.pack(fill="both", expand=True)

        for tag, fg in [("ok", GREEN), ("warn", YELLOW), ("error", RED)]:
            self._tree.tag_configure(tag, foreground=fg)

        footer = tk.Frame(parent, bg=BG2)
        footer.pack(fill="x", padx=4, pady=(0, 4))

        self._summary_lbl = tk.Label(footer, text="", font=FONT_UI, bg=BG2, fg=FG2, anchor="w")
        self._summary_lbl.pack(side="left")

        tk.Button(footer, text="📂 Rapports", command=lambda: self._open_folder(REPORTS_DIR),
                  bg=BG3, fg=FG2, font=FONT_UI, relief="flat",
                  padx=8, pady=3, cursor="hand2").pack(side="right")
        tk.Button(footer, text="Exporter JSON", command=self._export_report_json,
                  bg=BG3, fg=FG2, font=FONT_UI, relief="flat",
                  padx=8, pady=3, cursor="hand2").pack(side="right", padx=(0, 4))
        self._html_btn = tk.Button(footer, text="🌐 Exporter HTML",
                                    command=self._export_report_html,
                                    bg=ACCENT, fg=BG,
                                    font=("Segoe UI Semibold", 10),
                                    relief="flat", padx=8, pady=3, cursor="hand2")
        self._html_btn.pack(side="right", padx=(0, 4))

    def _build_stats_tab(self, parent):
        top = tk.Frame(parent, bg=BG2)
        top.pack(fill="x", padx=8, pady=(8, 4))

        tk.Label(top, text="Session :", bg=BG2, fg=FG2, font=FONT_UI).pack(side="left")
        self._stats_session_var = tk.StringVar()
        self._stats_session_cb  = ttk.Combobox(top, textvariable=self._stats_session_var,
                                                state="readonly", width=40)
        self._stats_session_cb.pack(side="left", padx=(6, 0))
        self._stats_session_cb.bind("<<ComboboxSelected>>", lambda _: self._refresh_stats())

        tk.Button(top, text="🔄 Actualiser", command=self._refresh_stats,
                  bg=BG3, fg=FG2, font=FONT_UI, relief="flat",
                  padx=8, pady=3, cursor="hand2").pack(side="left", padx=(8, 0))
        tk.Button(top, text="⬇ Export CSV", command=self._export_csv,
                  bg=GREEN, fg=BG, font=("Segoe UI Semibold", 10),
                  relief="flat", padx=8, pady=3, cursor="hand2").pack(side="left", padx=(4, 0))
        tk.Button(top, text="🌐 Dashboard Web", command=self._open_dashboard,
                  bg=BG3, fg=ACCENT, font=FONT_UI, relief="flat",
                  padx=8, pady=3, cursor="hand2").pack(side="right")

        # Notebook interne : Runs / Labels
        nb2 = ttk.Notebook(parent, style="RPA.TNotebook")
        nb2.pack(fill="both", expand=True, padx=4, pady=4)

        runs_tab   = tk.Frame(nb2, bg=BG2)
        labels_tab = tk.Frame(nb2, bg=BG2)
        nb2.add(runs_tab,   text="Historique des runs")
        nb2.add(labels_tab, text="Stats par bouton")

        # Treeview runs
        run_cols = ("Run #", "Démarré le", "Total", "✔ OK", "⚠ Ignorées", "✘ Erreurs",
                    "Avg (ms)", "Max (ms)")
        sb_r = tk.Scrollbar(runs_tab)
        sb_r.pack(side="right", fill="y")
        self._runs_tree = ttk.Treeview(runs_tab, columns=run_cols, show="headings",
                                        style="RPA.Treeview", yscrollcommand=sb_r.set)
        for c in run_cols:
            self._runs_tree.heading(c, text=c)
            self._runs_tree.column(c, width=90, stretch=True)
        self._runs_tree.column("Run #",      width=55, stretch=False)
        self._runs_tree.column("Démarré le", width=150, stretch=True)
        sb_r.config(command=self._runs_tree.yview)
        self._runs_tree.pack(fill="both", expand=True)
        for tag, fg in [("ok", GREEN), ("warn", YELLOW), ("error", RED)]:
            self._runs_tree.tag_configure(tag, foreground=fg)

        # Treeview labels
        lbl_cols = ("Cible", "Type", "Exécutions", "Avg (ms)", "Max (ms)", "Min (ms)", "Taux OK")
        sb_l = tk.Scrollbar(labels_tab)
        sb_l.pack(side="right", fill="y")
        self._labels_tree = ttk.Treeview(labels_tab, columns=lbl_cols, show="headings",
                                          style="RPA.Treeview", yscrollcommand=sb_l.set)
        for c in lbl_cols:
            self._labels_tree.heading(c, text=c)
            self._labels_tree.column(c, width=100, stretch=True)
        self._labels_tree.column("Cible",       width=200, stretch=True)
        self._labels_tree.column("Type",        width=80,  stretch=False)
        self._labels_tree.column("Exécutions",  width=80,  stretch=False)
        sb_l.config(command=self._labels_tree.yview)
        self._labels_tree.pack(fill="both", expand=True)
        for tag, fg in [("ok", GREEN), ("warn", YELLOW), ("error", RED)]:
            self._labels_tree.tag_configure(tag, foreground=fg)

        self._stats_summary_lbl = tk.Label(parent, text="", font=FONT_UI,
                                            bg=BG2, fg=FG2, anchor="w")
        self._stats_summary_lbl.pack(fill="x", padx=8, pady=(0, 4))

        # Charge la liste des sessions au démarrage
        self.after(500, self._load_stats_sessions)

    # ── Moniteurs ──────────────────────────────────────────────────────────────

    def _update_monitor_status(self):
        try:
            self._monitor_var.set(f"🖥  {monitor_summary()}")
        except Exception:
            pass

    # ── Sessions ──────────────────────────────────────────────────────────────

    def _refresh_session_list(self):
        self._session_listbox.delete(0, "end")
        sessions = sorted(SESSIONS_DIR.glob("session_*.json"), reverse=True)
        for s in sessions:
            self._session_listbox.insert("end", s.name)
        if sessions:
            self._session_listbox.selection_set(0)
            self._on_session_select(None)

    def _on_session_select(self, _event):
        sel = self._session_listbox.curselection()
        if not sel:
            return
        name = self._session_listbox.get(sel[0])
        self._session_path = SESSIONS_DIR / name
        self._replay_btn.config(state="normal")
        self._status_var.set(f"Session : {name}")

    def _browse_session(self):
        path = filedialog.askopenfilename(
            title="Choisir une session", initialdir=SESSIONS_DIR,
            filetypes=[("JSON", "*.json"), ("Tous", "*.*")],
        )
        if path:
            self._session_path = Path(path)
            self._replay_btn.config(state="normal")
            self._status_var.set(f"Session : {Path(path).name}")

    # ── Enregistrement ────────────────────────────────────────────────────────

    def _toggle_record(self):
        if self._recorder is None:
            self._recorder = ActionRecorder(
                save_screenshots=self._screenshots_rec_var.get()
            )
            self._recorder.start()
            self._rec_btn.config(text="  ■  STOP RECORD", bg=RED)
            self._replay_btn.config(state="disabled")
            self._status_var.set("⬤ Enregistrement en cours…")
            self._log("⬤ Enregistrement démarré.", "heading")
        else:
            path = self._recorder.stop()
            self._recorder = None
            self._rec_btn.config(text="  ⬤  RECORD", bg=GREEN)
            self._log(f"■ Session sauvegardée : {path.name}", "ok")
            self._status_var.set(f"Session : {path.name}")
            self._refresh_session_list()
            self._replay_btn.config(state="normal")

    # ── Replay ────────────────────────────────────────────────────────────────

    def _start_replay(self):
        if not self._session_path or not self._session_path.exists():
            messagebox.showwarning("Session introuvable",
                                   "Sélectionnez ou enregistrez d'abord une session.")
            return

        n_runs   = max(1, self._n_runs_var.get())
        interval = max(0.0, self._interval_var.get())
        capture  = self._screenshots_replay_var.get()

        self._results.clear()
        self._report_json_path = None
        self._report_html_path = None
        self._clear_tree()
        self._replay_btn.config(state="disabled")
        self._stop_btn.config(state="normal")
        self._progress_var.set(0)
        self._current_run_index  = 0
        self._total_runs_planned = n_runs

        run_label = f"Run 1/{n_runs}" if n_runs > 1 else ""
        self._run_lbl.config(text=run_label)
        self._status_var.set("Replay en cours…")
        self._notebook.select(0)

        tag = "heading" if n_runs == 1 else "run"
        self._log(f"▶ Replay × {n_runs} — session : {self._session_path.name}", tag)
        if n_runs > 1:
            self._log(f"  Intervalle entre runs : {interval}s | Screenshots : {capture}", "info")

        if n_runs == 1:
            self._replayer = ActionReplayer(
                ocr_similarity_min=self._ocr_threshold_var.get(),
                capture_screenshots=capture,
                on_progress=self._on_action_progress,
            )
            session = self._replayer.load_session(self._session_path)
            self._total_actions = len(session.get("actions", []))
            self._replay_thread = threading.Thread(
                target=self._run_single_replay, args=(session,), daemon=True
            )
        else:
            self._multi_runner = MultiReplayRunner(
                ocr_similarity_min=self._ocr_threshold_var.get(),
                capture_screenshots=capture,
                on_run_start=self._on_multi_run_start,
                on_run_done=self._on_multi_run_done,
                on_progress=self._on_action_progress,
            )
            # Lit le session une fois pour connaître le total
            with open(self._session_path, encoding="utf-8") as f:
                _s = json.load(f)
            self._total_actions = len(_s.get("actions", []))
            self._replay_thread = threading.Thread(
                target=self._run_multi_replay,
                args=(n_runs, interval),
                daemon=True,
            )

        self._replay_thread.start()

    def _run_single_replay(self, session: dict):
        try:
            results  = self._replayer.replay(session)
            self._results = results
            json_path = self._replayer.save_report(self._session_path)
            html_path = Path(str(json_path).replace(".json", ".html"))
            self._replayer.save_to_db(self._session_path)
            self.after(0, self._on_replay_done, results, json_path, html_path)
        except Exception as e:
            self.after(0, self._log, f"ERREUR replay : {e}", "error")
            self.after(0, self._on_replay_finished)

    def _run_multi_replay(self, n_runs: int, interval: float):
        try:
            all_res = self._multi_runner.run_n_times(
                self._session_path, n=n_runs, interval_s=interval, save_to_db=True
            )
            # Dernier run → rapport HTML
            if all_res:
                last_results = all_res[-1]
                self._results = last_results
                # Crée un replayer factice pour générer le rapport HTML du dernier run
                rep = ActionReplayer(capture_screenshots=False)
                rep._results = last_results
                json_path = rep.save_report(self._session_path)
                html_path = Path(str(json_path).replace(".json", ".html"))
            else:
                json_path = html_path = None
            self.after(0, self._on_multi_all_done, all_res, json_path, html_path)
        except Exception as e:
            self.after(0, self._log, f"ERREUR multi-run : {e}", "error")
            self.after(0, self._on_replay_finished)

    def _stop_replay(self):
        if self._replayer:
            self._replayer.stop()
        if self._multi_runner:
            self._multi_runner.stop()
        self._log("■ Replay interrompu par l'utilisateur.", "warn")

    def _on_multi_run_start(self, run_idx: int, total: int):
        self._current_run_index = run_idx
        self.after(0, self._run_lbl.config, {"text": f"Run {run_idx}/{total}"})
        self.after(0, self._log,
                   f"═══ Run {run_idx}/{total} ═══", "run")
        self.after(0, self._progress_var.set, 0)
        self.after(0, self._clear_tree)

    def _on_multi_run_done(self, run_idx: int, total: int, results: list[ActionResult]):
        ok    = sum(1 for r in results if r.status == "ok")
        times = [r.response_time_ms for r in results if r.response_time_ms is not None]
        avg_t = f"{sum(times)/len(times):.0f}ms" if times else "—"
        self.after(0, self._log,
                   f"✔ Run {run_idx}/{total} terminé — OK:{ok}/{len(results)} avg:{avg_t}", "ok")
        self.after(0, self._update_summary, results)
        if run_idx == total:
            self.after(0, self._load_stats_sessions)

    def _on_action_progress(self, current: int, total: int, result: ActionResult):
        self.after(0, self._update_progress, current, total, result)

    def _update_progress(self, current: int, total: int, result: ActionResult):
        pct = (current / total * 100) if total > 0 else 0
        self._progress_var.set(pct)
        self._progress_lbl.config(text=f"{current} / {total}")

        label = result.label or ""
        if result.skipped:
            tag, status = "warn", f"IGNORÉ — {result.error or ''}"
        elif result.error:
            tag, status = "error", f"ERREUR — {result.error}"
        else:
            rt   = f"{result.response_time_ms:.0f}ms" if result.response_time_ms is not None else "—"
            tag, status = "ok", f"OK  ⏱ {rt}"

        label_part = f"  [{label}]" if label else ""
        msg = (f"[{result.index:>3}] {result.action_type:<14}"
               f"{label_part:<22}  {status}")
        self._log(msg, tag)
        self._add_tree_row(result)

    def _on_replay_done(self, results: list[ActionResult],
                        json_path: Path, html_path: Path):
        self._report_json_path = json_path
        self._report_html_path = html_path if html_path and html_path.exists() else None
        self._on_replay_finished()
        self._log(f"✔ Replay terminé. JSON: {json_path.name}", "ok")
        if self._report_html_path:
            self._log(f"   HTML: {html_path.name}", "ok")
        self._status_var.set("Replay terminé.")
        self._notebook.select(1)
        self._update_summary(results)
        self._load_stats_sessions()

    def _on_multi_all_done(self, all_res, json_path, html_path):
        n = len(all_res)
        self._log(f"✔ {n} run(s) terminés — données persistées en DB.", "run")
        if json_path:
            self._report_json_path = json_path
            self._report_html_path = html_path if html_path and html_path.exists() else None
        self._on_replay_finished()
        self._status_var.set(f"{n} run(s) terminé(s).")
        self._notebook.select(2)   # → onglet Stats
        self._load_stats_sessions()

    def _on_replay_finished(self):
        self._replay_btn.config(state="normal")
        self._stop_btn.config(state="disabled")
        self._progress_var.set(100)
        self._run_lbl.config(text="")

    # ── Rapport ───────────────────────────────────────────────────────────────

    def _add_tree_row(self, r: ActionResult):
        ocr_score = f"{r.ocr_match:.2f}" if r.ocr_match is not None else "—"
        visual_ok = "✔" if r.visual_ok else ("✘" if r.visual_ok is False else "—")
        resp      = f"{r.response_time_ms:.0f}" if r.response_time_ms is not None else "—"
        label     = r.label or "—"

        if r.skipped:
            tag, status = "warn", "IGNORÉ"
        elif r.error:
            tag, status = "error", r.error[:50]
        else:
            tag, status = "ok", "OK"

        iid = self._tree.insert("", "end",
                                 values=(r.index, r.action_type, label,
                                         ocr_score, visual_ok, resp, status))
        self._tree.item(iid, tags=(tag,))

    def _clear_tree(self):
        for item in self._tree.get_children():
            self._tree.delete(item)
        self._summary_lbl.config(text="")

    def _update_summary(self, results: list[ActionResult]):
        total  = len(results)
        ok     = sum(1 for r in results if r.status == "ok")
        skip   = sum(1 for r in results if r.status == "skip")
        errors = sum(1 for r in results if r.status == "error")
        times  = [r.response_time_ms for r in results if r.response_time_ms is not None]
        avg_t  = f"{sum(times)/len(times):.0f}ms" if times else "—"
        max_t  = f"{max(times):.0f}ms" if times else "—"
        self._summary_lbl.config(
            text=f"Total {total}  ✔ OK {ok}  ⚠ Ignorées {skip}  ✘ Erreurs {errors}"
                 f"   ⏱ Avg {avg_t}  Max {max_t}"
        )

    def _export_report_json(self):
        if not self._results:
            messagebox.showinfo("Rapport vide", "Aucun résultat disponible.")
            return
        path = filedialog.asksaveasfilename(
            title="Exporter le rapport JSON", initialdir=REPORTS_DIR,
            defaultextension=".json", filetypes=[("JSON", "*.json")],
        )
        if path:
            data = [r.to_dict() for r in self._results]
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            self._log(f"Rapport JSON exporté → {path}", "ok")

    def _export_report_html(self):
        if not self._results:
            messagebox.showinfo("Rapport vide", "Aucun résultat disponible.")
            return
        if self._report_html_path and self._report_html_path.exists():
            ans = messagebox.askyesnocancel(
                "Rapport HTML",
                f"Rapport existant : {self._report_html_path.name}\nOuvrir ce fichier ?",
            )
            if ans is None:
                return
            if ans:
                self._open_html(self._report_html_path)
                return

        path = filedialog.asksaveasfilename(
            title="Exporter le rapport HTML", initialdir=REPORTS_DIR,
            defaultextension=".html", filetypes=[("HTML", "*.html")],
        )
        if not path:
            return
        rep = ActionReplayer()
        rep._results = self._results
        ts   = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        stem = (self._session_path.stem if self._session_path else "session")
        html = rep._build_html_report(rep._build_report_dict(
            self._session_path or Path("session.json"), ts), stem, ts)
        Path(path).write_text(html, encoding="utf-8")
        self._log(f"Rapport HTML exporté → {path}", "ok")
        self._open_html(Path(path))

    # ── Stats long-terme ──────────────────────────────────────────────────────

    def _load_stats_sessions(self):
        try:
            sessions = stats_db.get_all_sessions()
            values   = [f"{s['name']}  (id={s['id']}, {s.get('run_count',0)} runs)"
                        for s in sessions]
            self._stats_session_cb["values"] = values
            self._stats_sessions_data        = sessions
            if sessions and not self._stats_session_var.get():
                self._stats_session_cb.current(0)
                self._refresh_stats()
        except Exception:
            pass

    def _refresh_stats(self):
        idx = self._stats_session_cb.current()
        if idx < 0 or not hasattr(self, "_stats_sessions_data"):
            return
        sessions = self._stats_sessions_data
        if idx >= len(sessions):
            return
        sid = sessions[idx]["id"]

        # Runs
        for item in self._runs_tree.get_children():
            self._runs_tree.delete(item)
        runs = stats_db.get_session_runs(sid)
        for r in runs:
            pct = (r["ok_count"] * 100 // r["total"]) if r.get("total") else 0
            tag = "ok" if pct == 100 else ("warn" if pct >= 70 else "error")
            avg = f"{r['avg_response_ms']:.0f}" if r.get("avg_response_ms") is not None else "—"
            mx  = f"{r['max_response_ms']:.0f}" if r.get("max_response_ms") is not None else "—"
            iid = self._runs_tree.insert("", "end", values=(
                f"#{r['run_number']}",
                (r["started_at"] or "").replace("T", " ")[:19],
                r.get("total", "—"),
                r["ok_count"],
                r["skip_count"],
                r["error_count"],
                avg,
                mx,
            ))
            self._runs_tree.item(iid, tags=(tag,))

        # Labels
        for item in self._labels_tree.get_children():
            self._labels_tree.delete(item)
        label_stats = stats_db.get_label_stats(sid)
        for l in label_stats:
            sr  = l.get("success_rate") or 0
            tag = "ok" if sr >= 95 else ("warn" if sr >= 70 else "error")
            avg = f"{l['avg_ms']:.0f}" if l.get("avg_ms") is not None else "—"
            mx  = f"{l['max_ms']:.0f}" if l.get("max_ms") is not None else "—"
            mn  = f"{l['min_ms']:.0f}" if l.get("min_ms") is not None else "—"
            iid = self._labels_tree.insert("", "end", values=(
                l.get("label") or "—",
                l.get("action_type") or "—",
                l.get("run_count", "—"),
                avg, mx, mn,
                f"{sr:.1f}%",
            ))
            self._labels_tree.item(iid, tags=(tag,))

        s = sessions[idx]
        self._stats_summary_lbl.config(
            text=f"{s['name']} — {s.get('run_count',0)} run(s) — "
                 f"{s.get('action_count',0)} actions"
        )

    def _export_csv(self):
        idx = self._stats_session_cb.current()
        if idx < 0 or not hasattr(self, "_stats_sessions_data"):
            messagebox.showinfo("Aucune session", "Sélectionnez une session dans la liste.")
            return
        sid  = self._stats_sessions_data[idx]["id"]
        name = self._stats_sessions_data[idx]["name"]
        path = filedialog.asksaveasfilename(
            title="Exporter le CSV", initialdir=REPORTS_DIR,
            defaultextension=".csv",
            initialfile=f"{name}_export.csv",
            filetypes=[("CSV", "*.csv"), ("Tous", "*.*")],
        )
        if not path:
            return
        try:
            csv_data = stats_db.export_csv(sid)
            Path(path).write_text(csv_data, encoding="utf-8-sig")
            self._log(f"CSV exporté → {path}", "ok")
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
                self._log(f"🌐 Dashboard lancé → {url}", "heading")
                self.after(1500, lambda: webbrowser.open(url))
            except Exception as e:
                messagebox.showerror("Erreur Dashboard", str(e))
        else:
            self._log(f"🌐 Dashboard déjà actif → {url}", "info")
            webbrowser.open(url)

    # ── Journal ───────────────────────────────────────────────────────────────

    def _log(self, message: str, tag: str = "info"):
        ts   = datetime.datetime.now().strftime("%H:%M:%S")
        line = f"[{ts}] {message}\n"
        self._log_text.config(state="normal")
        self._log_text.insert("end", line, tag)
        self._log_text.see("end")
        self._log_text.config(state="disabled")

    # ── Utilitaires ───────────────────────────────────────────────────────────

    @staticmethod
    def _open_folder(path: Path):
        import os
        if sys.platform == "win32":
            os.startfile(str(path))
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(path)])
        else:
            subprocess.Popen(["xdg-open", str(path)])

    @staticmethod
    def _open_html(path: Path):
        webbrowser.open(path.as_uri())

    def _on_close(self):
        global _SERVER_PROC
        if _SERVER_PROC and _SERVER_PROC.poll() is None:
            _SERVER_PROC.terminate()
        self.destroy()


# ─── Lancement ────────────────────────────────────────────────────────────────

def main():
    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()
