"""
gui.py — Interface Tkinter pour enregistrer et rejouer des sessions.

v2 :
  • Colonne « Cible » dans le rapport Treeview (label OCR humain)
  • Colonne « Cible » affichée dans le journal temps réel
  • Bouton « Exporter HTML » avec graphique SVG des temps de réponse
  • Support multi-moniteurs : détection du nombre d'écrans + info dans la barre de statut
  • Fenêtre initiale centrée sur le moniteur principal

Fonctionnalités v1 conservées :
  • Bouton RECORD  : démarre/arrête l'enregistreur (recorder.py)
  • Sélection de session + bouton REPLAY
  • Arrêt anticipé du replay
  • Rapport de timing action-par-action avec graphique SVG embarqué
  • Barre de progression + log en temps réel
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import threading
import json
import time
import datetime
import subprocess
import sys
from pathlib import Path

# Imports locaux
try:
    from recorder import ActionRecorder, get_all_monitors
    from replayer import ActionReplayer, ActionResult, SESSIONS_DIR, REPORTS_DIR
except ImportError as e:
    import tkinter.messagebox as _mb
    _mb.showerror("Import manquant", str(e))
    sys.exit(1)

# ─── Palette & constantes ─────────────────────────────────────────────────────

BG        = "#1C1F26"
BG2       = "#252932"
BG3       = "#2E3440"
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
FONT_H2   = ("Segoe UI", 11)


# ─── Utilitaire multi-moniteurs ───────────────────────────────────────────────

def center_window_on_primary(win: tk.Tk, w: int = 940, h: int = 660):
    """Centre la fenêtre sur le moniteur principal."""
    monitors = get_all_monitors()
    primary = monitors[0]
    x = primary["left"] + (primary["width"]  - w) // 2
    y = primary["top"]  + (primary["height"] - h) // 2
    win.geometry(f"{w}x{h}+{x}+{y}")


def monitor_summary() -> str:
    """Retourne un résumé textuel des moniteurs détectés."""
    monitors = get_all_monitors()
    if len(monitors) == 1:
        m = monitors[0]
        return f"1 écran  {m['width']}×{m['height']}"
    parts = [f"{m['width']}×{m['height']}" for m in monitors]
    return f"{len(monitors)} écrans  " + "  +  ".join(parts)


# ─── Application principale ───────────────────────────────────────────────────

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("WinGhost RPA v2")
        self.configure(bg=BG)
        self.resizable(True, True)
        self.minsize(860, 640)
        center_window_on_primary(self)

        self._recorder: ActionRecorder | None = None
        self._replayer: ActionReplayer | None = None
        self._session_path: Path | None = None
        self._replay_thread: threading.Thread | None = None
        self._results: list[ActionResult] = []
        self._report_json_path: Path | None = None
        self._report_html_path: Path | None = None

        self._build_ui()
        self._refresh_session_list()
        # Affichage moniteurs dans la barre de statut
        self.after(200, self._update_monitor_status)

    # ── Construction de l'interface ───────────────────────────────────────────

    def _build_ui(self):
        # ── En-tête ──────────────────────────────────────────────────────────
        header = tk.Frame(self, bg=BG, pady=10)
        header.pack(fill="x", padx=20)
        tk.Label(header, text="WinGhost RPA v2",
                 font=FONT_H1, bg=BG, fg=FG).pack(side="left")

        self._status_var = tk.StringVar(value="Prêt")
        tk.Label(header, textvariable=self._status_var,
                 font=FONT_UI, bg=BG, fg=FG2).pack(side="right", padx=10)

        # Indicateur multi-moniteurs
        self._monitor_var = tk.StringVar(value="")
        tk.Label(header, textvariable=self._monitor_var,
                 font=("Segoe UI", 9), bg=BG, fg=FG2).pack(side="right", padx=(0, 16))

        sep = tk.Frame(self, bg=BG3, height=1)
        sep.pack(fill="x", padx=20)

        # ── Panneau principal (gauche + droite) ───────────────────────────────
        main = tk.Frame(self, bg=BG)
        main.pack(fill="both", expand=True, padx=20, pady=10)

        left  = tk.Frame(main, bg=BG, width=280)
        left.pack(side="left", fill="y", padx=(0, 12))
        left.pack_propagate(False)

        right = tk.Frame(main, bg=BG)
        right.pack(side="left", fill="both", expand=True)

        self._build_left_panel(left)
        self._build_right_panel(right)

    def _build_left_panel(self, parent):
        # ── RECORD ───────────────────────────────────────────────────────────
        rec_frame = tk.LabelFrame(parent, text=" ⬤  Enregistrement ",
                                  font=FONT_UI, bg=BG2, fg=FG,
                                  bd=1, relief="flat", padx=10, pady=10)
        rec_frame.pack(fill="x", pady=(0, 12))

        self._screenshots_var = tk.BooleanVar(value=False)
        tk.Checkbutton(rec_frame, text="Capturer les screenshots",
                       variable=self._screenshots_var,
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
                                   font=FONT_UI, bg=BG2, fg=FG,
                                   bd=1, relief="flat", padx=10, pady=10)
        sess_frame.pack(fill="both", expand=True, pady=(0, 12))

        sb = tk.Scrollbar(sess_frame)
        sb.pack(side="right", fill="y")

        self._session_listbox = tk.Listbox(
            sess_frame, bg=BG3, fg=FG, font=FONT_MONO,
            selectbackground=ACCENT, selectforeground=BG,
            relief="flat", highlightthickness=0,
            yscrollcommand=sb.set,
        )
        self._session_listbox.pack(fill="both", expand=True)
        sb.config(command=self._session_listbox.yview)
        self._session_listbox.bind("<<ListboxSelect>>", self._on_session_select)

        btns = tk.Frame(sess_frame, bg=BG2)
        btns.pack(fill="x", pady=(6, 0))

        tk.Button(btns, text="Rafraîchir",
                  command=self._refresh_session_list,
                  bg=BG3, fg=FG2, font=FONT_UI,
                  relief="flat", padx=6, pady=3, cursor="hand2",
                  ).pack(side="left")
        tk.Button(btns, text="Parcourir…",
                  command=self._browse_session,
                  bg=BG3, fg=FG2, font=FONT_UI,
                  relief="flat", padx=6, pady=3, cursor="hand2",
                  ).pack(side="left", padx=(4, 0))

        # ── Options replay ────────────────────────────────────────────────────
        opt_frame = tk.LabelFrame(parent, text=" ⚙  Options ",
                                  font=FONT_UI, bg=BG2, fg=FG,
                                  bd=1, relief="flat", padx=10, pady=8)
        opt_frame.pack(fill="x", pady=(0, 12))

        tk.Label(opt_frame, text="Seuil OCR :", bg=BG2, fg=FG2,
                 font=FONT_UI).grid(row=0, column=0, sticky="w")
        self._ocr_threshold_var = tk.DoubleVar(value=0.40)
        ocr_slider = tk.Scale(
            opt_frame, variable=self._ocr_threshold_var,
            from_=0.0, to=1.0, resolution=0.05, orient="horizontal",
            bg=BG2, fg=FG, troughcolor=BG3, highlightthickness=0,
            sliderrelief="flat", font=FONT_UI,
        )
        ocr_slider.grid(row=0, column=1, sticky="ew", padx=(6, 0))
        opt_frame.columnconfigure(1, weight=1)

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
        self._stop_btn.pack(fill="x")

    def _build_right_panel(self, parent):
        # ── Progression ───────────────────────────────────────────────────────
        prog_frame = tk.Frame(parent, bg=BG)
        prog_frame.pack(fill="x", pady=(0, 8))

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
            maximum=100, length=400,
        )
        self._progress.pack(fill="x", side="left", expand=True, padx=(0, 10))

        # ── Onglets : Log / Rapport ───────────────────────────────────────────
        nb_style = ttk.Style()
        nb_style.configure("RPA.TNotebook",
                            background=BG, borderwidth=0)
        nb_style.configure("RPA.TNotebook.Tab",
                            background=BG3, foreground=FG2,
                            padding=[12, 4], font=FONT_UI)
        nb_style.map("RPA.TNotebook.Tab",
                     background=[("selected", BG2)],
                     foreground=[("selected", FG)])

        self._notebook = ttk.Notebook(parent, style="RPA.TNotebook")
        self._notebook.pack(fill="both", expand=True)

        # Onglet Log
        log_tab = tk.Frame(self._notebook, bg=BG2)
        self._notebook.add(log_tab, text="Journal")

        self._log_text = tk.Text(
            log_tab, bg=BG2, fg=FG, font=FONT_MONO,
            relief="flat", highlightthickness=0,
            state="disabled", wrap="word",
        )
        log_scroll = tk.Scrollbar(log_tab, command=self._log_text.yview)
        self._log_text.configure(yscrollcommand=log_scroll.set)
        log_scroll.pack(side="right", fill="y")
        self._log_text.pack(fill="both", expand=True, padx=2, pady=2)

        self._log_text.tag_configure("ok",      foreground=GREEN)
        self._log_text.tag_configure("warn",     foreground=YELLOW)
        self._log_text.tag_configure("error",    foreground=RED)
        self._log_text.tag_configure("info",     foreground=FG2)
        self._log_text.tag_configure("heading",  foreground=ACCENT,
                                     font=("Consolas", 9, "bold"))
        self._log_text.tag_configure("label",    foreground=ACCENT2)

        # Onglet Rapport
        report_tab = tk.Frame(self._notebook, bg=BG2)
        self._notebook.add(report_tab, text="Rapport")
        self._build_report_tab(report_tab)

    def _build_report_tab(self, parent):
        # v2 : colonne « Cible » ajoutée
        cols = ("#", "Type", "Cible", "OCR Score", "Visuel OK", "Réponse (s)", "Statut")
        tree_frame = tk.Frame(parent, bg=BG2)
        tree_frame.pack(fill="both", expand=True, padx=4, pady=4)

        tree_scroll = tk.Scrollbar(tree_frame)
        tree_scroll.pack(side="right", fill="y")

        ts = ttk.Style()
        ts.configure("RPA.Treeview",
                     background=BG3, fieldbackground=BG3,
                     foreground=FG, rowheight=22, font=FONT_MONO,
                     borderwidth=0)
        ts.configure("RPA.Treeview.Heading",
                     background=BG2, foreground=ACCENT,
                     font=("Segoe UI Semibold", 9))
        ts.map("RPA.Treeview",
               background=[("selected", ACCENT)],
               foreground=[("selected", BG)])

        self._tree = ttk.Treeview(
            tree_frame, columns=cols, show="headings",
            style="RPA.Treeview",
            yscrollcommand=tree_scroll.set,
        )
        for col in cols:
            self._tree.heading(col, text=col)
        self._tree.column("#",           width=40,  stretch=False)
        self._tree.column("Type",        width=100, stretch=False)
        self._tree.column("Cible",       width=180, stretch=True)   # v2
        self._tree.column("OCR Score",   width=75,  stretch=False)
        self._tree.column("Visuel OK",   width=70,  stretch=False)
        self._tree.column("Réponse (s)", width=90,  stretch=False)
        self._tree.column("Statut",      width=160, stretch=True)

        tree_scroll.config(command=self._tree.yview)
        self._tree.pack(fill="both", expand=True)

        # Pied du rapport
        footer = tk.Frame(parent, bg=BG2)
        footer.pack(fill="x", padx=4, pady=(0, 4))

        self._summary_lbl = tk.Label(
            footer, text="", font=FONT_UI, bg=BG2, fg=FG2, anchor="w"
        )
        self._summary_lbl.pack(side="left")

        # ── Boutons export ────────────────────────────────────────────────────
        tk.Button(
            footer, text="📂 Dossier rapports",
            command=lambda: self._open_folder(REPORTS_DIR),
            bg=BG3, fg=FG2, font=FONT_UI,
            relief="flat", padx=8, pady=3, cursor="hand2",
        ).pack(side="right")

        tk.Button(
            footer, text="Exporter JSON",
            command=self._export_report_json,
            bg=BG3, fg=FG2, font=FONT_UI,
            relief="flat", padx=8, pady=3, cursor="hand2",
        ).pack(side="right", padx=(0, 4))

        # v2 : bouton export HTML
        self._html_btn = tk.Button(
            footer, text="🌐 Exporter HTML",
            command=self._export_report_html,
            bg=ACCENT, fg=BG, font=("Segoe UI Semibold", 10),
            relief="flat", padx=8, pady=3, cursor="hand2",
        )
        self._html_btn.pack(side="right", padx=(0, 4))

    # ── Multi-moniteurs ───────────────────────────────────────────────────────

    def _update_monitor_status(self):
        """Met à jour l'indicateur écrans dans le header."""
        try:
            txt = monitor_summary()
            self._monitor_var.set(f"🖥  {txt}")
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
            title="Choisir une session",
            initialdir=SESSIONS_DIR,
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
                save_screenshots=self._screenshots_var.get()
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
            self._status_var.set(f"Session enregistrée : {path.name}")
            self._refresh_session_list()
            self._replay_btn.config(state="normal")

    # ── Replay ────────────────────────────────────────────────────────────────

    def _start_replay(self):
        if not self._session_path or not self._session_path.exists():
            messagebox.showwarning("Session introuvable",
                                   "Sélectionnez ou enregistrez d'abord une session.")
            return

        self._results.clear()
        self._report_json_path = None
        self._report_html_path = None
        self._clear_tree()
        self._log(f"▶ Début du replay : {self._session_path.name}", "heading")
        self._replay_btn.config(state="disabled")
        self._stop_btn.config(state="normal")
        self._progress_var.set(0)
        self._status_var.set("Replay en cours…")
        self._notebook.select(0)

        self._replayer = ActionReplayer(
            ocr_similarity_min=self._ocr_threshold_var.get(),
            on_progress=self._on_action_progress,
        )

        session = self._replayer.load_session(self._session_path)
        self._total_actions = len(session.get("actions", []))

        self._replay_thread = threading.Thread(
            target=self._run_replay,
            args=(session,),
            daemon=True,
        )
        self._replay_thread.start()

    def _run_replay(self, session: dict):
        try:
            results = self._replayer.replay(session)
            self._results = results
            json_path = self._replayer.save_report(self._session_path)
            # Le HTML a été généré en même temps par save_report()
            html_path = Path(str(json_path).replace(".json", ".html"))
            self.after(0, self._on_replay_done, results, json_path, html_path)
        except Exception as e:
            self.after(0, self._log, f"ERREUR replay : {e}", "error")
            self.after(0, self._on_replay_finished)

    def _stop_replay(self):
        if self._replayer:
            self._replayer.stop()
        self._log("■ Replay interrompu par l'utilisateur.", "warn")

    def _on_action_progress(self, current: int, total: int, result: ActionResult):
        self.after(0, self._update_progress, current, total, result)

    def _update_progress(self, current: int, total: int, result: ActionResult):
        pct = (current / total * 100) if total > 0 else 0
        self._progress_var.set(pct)
        self._progress_lbl.config(text=f"{current} / {total}")

        label = result.label or ""

        if result.skipped:
            tag = "warn"
            status = f"IGNORÉ — {result.error or ''}"
        elif result.error:
            tag = "error"
            status = f"ERREUR — {result.error}"
        else:
            tag = "ok"
            rt   = f"{result.response_time:.3f}s" if result.response_time is not None else "—"
            status = f"OK  ⏱ {rt}"

        # v2 : label affiché dans le journal
        label_part = f"  [{label}]" if label else ""
        msg = (f"[{result.index:>3}] {result.action_type:<14}"
               f"{label_part:<22}"
               f"  OCR={result.ocr_match:.2f if result.ocr_match is not None else '—':>5}"
               f"  {status}")
        self._log(msg, tag)
        self._add_tree_row(result)

    def _on_replay_done(self, results: list[ActionResult],
                        json_path: Path, html_path: Path):
        self._report_json_path = json_path
        self._report_html_path = html_path if html_path.exists() else None
        self._on_replay_finished()
        self._log(f"✔ Replay terminé. JSON: {json_path.name}", "ok")
        if self._report_html_path:
            self._log(f"   HTML: {html_path.name}", "ok")
        self._status_var.set("Replay terminé.")
        self._notebook.select(1)
        self._update_summary(results)

    def _on_replay_finished(self):
        self._replay_btn.config(state="normal")
        self._stop_btn.config(state="disabled")
        self._progress_var.set(100)

    # ── Rapport ───────────────────────────────────────────────────────────────

    def _add_tree_row(self, r: ActionResult):
        ocr_score = f"{r.ocr_match:.2f}" if r.ocr_match is not None else "—"
        visual_ok = "✔" if r.visual_ok else ("✘" if r.visual_ok is False else "—")
        resp      = f"{r.response_time:.3f}" if r.response_time is not None else "—"
        label     = r.label or "—"

        if r.skipped:
            tag, status = "warn", "IGNORÉ"
        elif r.error:
            tag, status = "error", r.error[:50]
        else:
            tag, status = "ok", "OK"

        iid = self._tree.insert(
            "", "end",
            values=(r.index, r.action_type, label,
                    ocr_score, visual_ok, resp, status),
        )
        self._tree.tag_configure("ok",    foreground=GREEN)
        self._tree.tag_configure("warn",  foreground=YELLOW)
        self._tree.tag_configure("error", foreground=RED)
        self._tree.item(iid, tags=(tag,))

    def _clear_tree(self):
        for item in self._tree.get_children():
            self._tree.delete(item)
        self._summary_lbl.config(text="")

    def _update_summary(self, results: list[ActionResult]):
        total  = len(results)
        ok     = sum(1 for r in results if not r.skipped and not r.error)
        skip   = sum(1 for r in results if r.skipped)
        errors = sum(1 for r in results if r.error)
        times  = [r.response_time for r in results if r.response_time is not None]
        avg_t  = f"{sum(times)/len(times):.3f}s" if times else "—"
        max_t  = f"{max(times):.3f}s" if times else "—"

        self._summary_lbl.config(
            text=f"Total {total}  ✔ OK {ok}  ⚠ Ignorées {skip}  ✘ Erreurs {errors}"
                 f"   ⏱ Avg {avg_t}  Max {max_t}"
        )

    def _export_report_json(self):
        if not self._results:
            messagebox.showinfo("Rapport vide", "Aucun résultat disponible.")
            return
        path = filedialog.asksaveasfilename(
            title="Exporter le rapport JSON",
            initialdir=REPORTS_DIR,
            defaultextension=".json",
            filetypes=[("JSON", "*.json")],
        )
        if path:
            data = [r.to_dict() for r in self._results]
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            self._log(f"Rapport JSON exporté → {path}", "ok")

    def _export_report_html(self):
        """v2 : exporte le rapport HTML avec graphique SVG et l'ouvre dans le navigateur."""
        if not self._results:
            messagebox.showinfo("Rapport vide", "Aucun résultat disponible.")
            return

        # Si on a déjà un rapport HTML généré, on propose de l'ouvrir directement
        if self._report_html_path and self._report_html_path.exists():
            answer = messagebox.askyesnocancel(
                "Rapport HTML",
                f"Un rapport HTML a déjà été généré :\n{self._report_html_path.name}\n\n"
                "Ouvrir ce fichier ?  (Non = en générer un nouveau)"
            )
            if answer is None:
                return
            if answer:
                self._open_html(self._report_html_path)
                return

        # Génère un nouveau fichier
        path = filedialog.asksaveasfilename(
            title="Exporter le rapport HTML",
            initialdir=REPORTS_DIR,
            defaultextension=".html",
            filetypes=[("HTML", "*.html")],
        )
        if not path:
            return

        html_path = Path(path)
        try:
            html_content = self._replayer.save_report_html(
                self._session_path or Path("session_unknown.json")
            )
            # save_report_html retourne le path, le contenu est déjà écrit
            # Mais on veut écrire à l'emplacement choisi par l'utilisateur
            html_content_str = self._replayer._build_html_report(
                {
                    "session_file": str(self._session_path),
                    "replayed_at":  datetime.datetime.now().strftime("%Y%m%d_%H%M%S"),
                    "summary": self._make_summary_dict(),
                    "actions": [r.to_dict() for r in self._results],
                },
                (self._session_path.stem if self._session_path else "session"),
                datetime.datetime.now().strftime("%Y%m%d_%H%M%S"),
            )
            html_path.write_text(html_content_str, encoding="utf-8")
            self._log(f"Rapport HTML exporté → {html_path}", "ok")
            self._open_html(html_path)
        except Exception as e:
            messagebox.showerror("Erreur HTML", str(e))

    def _make_summary_dict(self) -> dict:
        results = self._results
        times = [r.response_time for r in results if r.response_time is not None]
        return {
            "total":   len(results),
            "ok":      sum(1 for r in results if not r.skipped and not r.error),
            "skipped": sum(1 for r in results if r.skipped),
            "errors":  sum(1 for r in results if r.error),
            "avg_response_time_s": round(sum(times)/len(times), 3) if times else None,
            "max_response_time_s": round(max(times), 3) if times else None,
        }

    # ── Journal ───────────────────────────────────────────────────────────────

    def _log(self, message: str, tag: str = "info"):
        ts  = datetime.datetime.now().strftime("%H:%M:%S")
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
        """Ouvre le rapport HTML dans le navigateur par défaut."""
        import webbrowser
        webbrowser.open(path.as_uri())


# ─── Lancement ────────────────────────────────────────────────────────────────

def main():
    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()
