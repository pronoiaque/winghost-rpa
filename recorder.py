"""
recorder.py — Enregistrement des actions utilisateur (clics + saisies)
avec capture visuelle de la zone cible via EasyOCR.

v6.1 : capture de TOUS les inputs souris — clic milieu (middle_click),
       molette (scroll), glisser-déposer (drag press→release)

v6 : enregistrement des mouvements souris (action "move", throttlé)
     + paramètre `reader` pour réutiliser un lecteur OCR déjà chargé

v5 : ajout du champ `target_app` au niveau du scénario (nom d'application
     ciblée, saisi par l'utilisateur, inscrit tel quel dans le journal officiel)

v4 : ajout du champ `app_name` sur chaque Action (nom de l'application au
     premier plan au moment de l'action, via win32gui/psutil)
     + SCENARIOS_DIR pour la sortie des fichiers de scénario
     + scenario_name paramètre sur ActionRecorder
     + captures de screenshots toujours activées (padding 160 px)

v2 : ajout du champ `label` (nom humain de la cible déduit de l'OCR)
     + support multi-moniteurs (capture sur l'écran contenant le curseur)

Sortie : scenarios/scenario_YYYYMMDD_HHMMSS.json
"""

import json
import time
import threading
import datetime
import os
import logging
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Optional

import pyautogui
from PIL import Image
import numpy as np
from pynput import mouse, keyboard

from paths import data_dir

# EasyOCR est OPTIONNEL (v6.3+) : il tire PyTorch (lourd) et n'est requis que
# pour l'ancrage visuel. On l'importe paresseusement ; absent, l'enregistrement
# fonctionne sans label OCR (les screenshots restent capturés).
try:
    import easyocr
    _HAS_EASYOCR = True
except Exception:
    easyocr = None
    _HAS_EASYOCR = False

# ─── Configuration ────────────────────────────────────────────────────────────

SESSIONS_DIR = data_dir() / "sessions"
SESSIONS_DIR.mkdir(parents=True, exist_ok=True)

SCENARIOS_DIR = data_dir() / "scenarios"
SCENARIOS_DIR.mkdir(parents=True, exist_ok=True)

SCREENSHOT_PADDING = 160         # px autour du clic pour la capture visuelle (wider)
OCR_LANGUAGES      = ["fr", "en"]
DOUBLE_CLICK_GAP   = 0.3         # secondes max entre deux clics pour détecter un double-clic
LABEL_MAX_WORDS    = 4           # nombre max de mots dans un label auto-généré
MOVE_THROTTLE_S  = 0.10   # intervalle min entre deux mouvements enregistrés (s)
MOVE_MIN_DIST_PX = 15     # distance min (px) pour enregistrer un mouvement
DRAG_MIN_DIST_PX = 12     # distance min (px) entre press et release pour qualifier un glisser

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [RECORDER] %(levelname)s — %(message)s"
)
log = logging.getLogger("recorder")


# ─── Détection de l'application au premier plan ──────────────────────────────

def get_foreground_app() -> str:
    """
    Retourne le nom de l'application au premier plan (sans extension .exe).
    Utilise win32gui + win32process + psutil.
    En cas d'erreur (plateforme non Windows, accès refusé, etc.), retourne "".
    Ne lève jamais d'exception.
    """
    try:
        import win32gui
        import win32process
        import psutil

        hwnd = win32gui.GetForegroundWindow()
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        name = psutil.Process(pid).name().removesuffix(".exe")
        return name
    except Exception:
        return ""


# ─── Multi-moniteurs ─────────────────────────────────────────────────────────

def get_all_monitors() -> list[dict]:
    """
    Retourne la liste des moniteurs {left, top, width, height}.
    Utilise screeninfo si disponible, sinon repli sur le moniteur principal pyautogui.
    """
    try:
        from screeninfo import get_monitors
        return [
            {"left": m.x, "top": m.y, "width": m.width, "height": m.height}
            for m in get_monitors()
        ]
    except Exception:
        w, h = pyautogui.size()
        return [{"left": 0, "top": 0, "width": w, "height": h}]


def monitor_for_point(x: int, y: int) -> dict:
    """Retourne le moniteur contenant le point (x, y)."""
    monitors = get_all_monitors()
    for m in monitors:
        if m["left"] <= x < m["left"] + m["width"] and \
           m["top"]  <= y < m["top"]  + m["height"]:
            return m
    # Repli : premier moniteur
    return monitors[0]


def screenshot_region(x: int, y: int, padding: int = SCREENSHOT_PADDING):
    """
    Capture une région carrée autour de (x, y) clampée aux limites
    du moniteur qui contient ce point.
    """
    mon = monitor_for_point(x, y)
    ml, mt, mw, mh = mon["left"], mon["top"], mon["width"], mon["height"]

    rx = max(ml, x - padding)
    ry = max(mt, y - padding)
    rr = min(ml + mw, x + padding)
    rb = min(mt + mh, y + padding)
    rw = rr - rx
    rh = rb - ry

    try:
        img = pyautogui.screenshot(region=(rx, ry, rw, rh))
    except Exception:
        # Certaines versions de pyautogui/Pillow ne gèrent pas les coords négatives
        img = pyautogui.screenshot()
        img = img.crop((rx - ml, ry - mt, rr - ml, rb - mt))

    return img, [rx, ry, rw, rh]


# ─── Génération du label humain ───────────────────────────────────────────────

def derive_label(ocr_text: str, action_type: str) -> str:
    """
    Déduit un label lisible depuis le texte OCR brut.

    Stratégie :
    1. Nettoie les séparateurs « | »
    2. Prend le fragment le plus court (probablement le bouton / l'étiquette)
       de longueur ≥ 2 caractères
    3. Limite à LABEL_MAX_WORDS mots
    4. Si rien, retourne un fallback selon le type d'action
    """
    if not ocr_text or not ocr_text.strip():
        fallbacks = {
            "click":        "Clic",
            "double_click": "Double-clic",
            "right_click":  "Clic droit",
            "type":         "Saisie",
            "key":          "Touche",
        }
        return fallbacks.get(action_type, "Action")

    # Séparer sur " | "
    fragments = [f.strip() for f in ocr_text.split("|") if f.strip()]

    if not fragments:
        return ocr_text[:40].strip()

    # Choisir le fragment le plus court qui a au moins 2 caractères
    candidates = sorted(fragments, key=len)
    chosen = next((c for c in candidates if len(c) >= 2), fragments[0])

    # Limiter à LABEL_MAX_WORDS mots
    words = chosen.split()
    if len(words) > LABEL_MAX_WORDS:
        chosen = " ".join(words[:LABEL_MAX_WORDS]) + "…"

    return chosen


# ─── Structures de données ────────────────────────────────────────────────────

@dataclass
class VisualContext:
    """Texte OCR extrait autour de la zone d'action (ancre visuelle)."""
    ocr_text: str                  # texte complet détecté dans la zone
    label: str                     # nom humain court déduit de l'OCR
    screenshot_region: list        # [x, y, w, h]
    screenshot_b64: Optional[str] = None  # PNG encodé base64


@dataclass
class Action:
    index:          int
    # "click" | "double_click" | "right_click" | "middle_click" | "drag"
    # | "scroll" | "move" | "type" | "key"
    action_type:    str
    timestamp:      float          # epoch
    x:              Optional[int]  = None
    y:              Optional[int]  = None
    x2:             Optional[int]  = None   # destination du glisser (drag)
    y2:             Optional[int]  = None
    button:         Optional[str]  = None
    scroll_dx:      Optional[int]  = None   # défilement horizontal (molette)
    scroll_dy:      Optional[int]  = None   # défilement vertical (molette)
    text:           Optional[str]  = None
    key:            Optional[str]  = None
    visual_context: Optional[dict] = None
    delay_before:   float          = 0.0   # délai depuis l'action précédente (s)
    app_name:       str            = ""    # nom de l'application au premier plan


# ─── Recorder principal ───────────────────────────────────────────────────────

class ActionRecorder:
    def __init__(self, scenario_name: str = "", target_app: str = "", reader=None):
        self._scenario_name = scenario_name
        self._target_app = target_app
        self.actions: list[Action] = []
        self.recording = False
        self._lock = threading.Lock()
        self._last_timestamp: float = 0.0
        self._action_index = 0
        self._pending_click: Optional[tuple] = None   # (x, y, button, t)
        self._press_info: Optional[tuple] = None      # (x, y, button, t) du bouton enfoncé
        self._button_down: bool = False               # un bouton souris est-il maintenu ?
        self._typed_buffer: str = ""
        self._last_key_time: float = 0.0
        self._mouse_listener  = None
        self._keyboard_listener = None
        self._last_move_time: float = 0.0
        self._last_move_x:    int   = 0
        self._last_move_y:    int   = 0

        if reader is not None:
            log.info("Utilisation du lecteur OCR partagé.")
            self._reader = reader
        elif _HAS_EASYOCR:
            log.info("Initialisation EasyOCR (langues : %s)…", OCR_LANGUAGES)
            self._reader = easyocr.Reader(OCR_LANGUAGES, gpu=False, verbose=False)
            log.info("EasyOCR prêt.")
        else:
            log.warning("EasyOCR indisponible — enregistrement sans label OCR "
                        "(les screenshots restent capturés).")
            self._reader = None

    # ── Contrôle ──────────────────────────────────────────────────────────────

    def start(self):
        self.recording = True
        self.actions.clear()
        self._action_index = 0
        self._last_timestamp = time.time()
        self._typed_buffer = ""

        self._mouse_listener = mouse.Listener(
            on_move=self._on_move,
            on_click=self._on_click,
            on_scroll=self._on_scroll,
        )
        self._keyboard_listener = keyboard.Listener(
            on_press=self._on_key_press,
            on_release=self._on_key_release
        )
        self._mouse_listener.start()
        self._keyboard_listener.start()
        log.info("⬤ Enregistrement démarré.")

    def stop(self) -> Path:
        self.recording = False
        self._flush_typed_buffer()

        if self._mouse_listener:
            self._mouse_listener.stop()
        if self._keyboard_listener:
            self._keyboard_listener.stop()

        path = self._save_session()
        log.info("■ Enregistrement arrêté. %d action(s) sauvegardée(s) → %s",
                 len(self.actions), path)
        return path

    # ── Handlers souris ───────────────────────────────────────────────────────

    def _on_click(self, x, y, button, pressed):
        if not self.recording:
            return

        t = time.time()
        btn_name = button.name  # "left" | "right" | "middle"

        # ── Relâchement : fin éventuelle d'un glisser (drag) ───────────────────
        if not pressed:
            self._button_down = False
            press = self._press_info
            self._press_info = None
            if press is None:
                return
            px, py, _pbtn, _pt = press
            dist = ((x - px) ** 2 + (y - py) ** 2) ** 0.5
            if dist >= DRAG_MIN_DIST_PX:
                # Convertit le clic enregistré au press en glisser (drag).
                with self._lock:
                    if self.actions and self.actions[-1].action_type in (
                            "click", "right_click", "middle_click"):
                        a = self.actions[-1]
                        a.action_type = "drag"
                        a.x2, a.y2 = x, y
                        self._pending_click = None
                        log.info("[%d] drag (%d,%d) → (%d,%d)",
                                 a.index, px, py, x, y)
            return

        # ── Enfoncement : clic / double-clic ───────────────────────────────────
        # Flush la saisie clavier en cours avant tout clic
        self._flush_typed_buffer()
        self._button_down = True
        self._press_info  = (x, y, btn_name, t)

        # Détection double-clic
        if (self._pending_click and
                btn_name == "left" and
                self._pending_click[2] == "left" and
                (t - self._pending_click[3]) <= DOUBLE_CLICK_GAP):
            # Remplace le clic simple précédent par un double-clic
            with self._lock:
                if self.actions and self.actions[-1].action_type == "click":
                    self.actions[-1].action_type = "double_click"
            self._pending_click = None
            log.debug("Double-clic détecté en (%d, %d)", x, y)
            return

        self._pending_click = (x, y, btn_name, t)

        action_type = {"right": "right_click",
                       "middle": "middle_click"}.get(btn_name, "click")
        visual = self._capture_visual_context(x, y, action_type)
        delay  = self._compute_delay(t)

        action = Action(
            index       = self._next_index(),
            action_type = action_type,
            timestamp   = t,
            x=x, y=y,
            button      = btn_name,
            visual_context = asdict(visual) if visual else None,
            delay_before   = delay,
            app_name       = get_foreground_app(),
        )
        with self._lock:
            self.actions.append(action)
        log.info("[%d] %s en (%d, %d) — label: %r — OCR: %r",
                 action.index, action_type, x, y,
                 visual.label if visual else "",
                 visual.ocr_text[:60] if visual else "")

    def _on_scroll(self, x: int, y: int, dx: int, dy: int):
        if not self.recording:
            return
        # Une molette valide souvent une saisie en cours → on la consigne avant
        self._flush_typed_buffer()
        t = time.time()
        delay = self._compute_delay(t)
        action = Action(
            index       = self._next_index(),
            action_type = "scroll",
            timestamp   = t,
            x=x, y=y,
            scroll_dx   = int(dx),
            scroll_dy   = int(dy),
            delay_before= delay,
            app_name    = get_foreground_app(),
        )
        with self._lock:
            self.actions.append(action)
        log.info("[%d] scroll (dx=%d, dy=%d) en (%d, %d)",
                 action.index, int(dx), int(dy), x, y)

    def _on_move(self, x: int, y: int):
        if not self.recording:
            return
        # Mouvement effectué bouton enfoncé → fait partie d'un glisser, ignoré ici
        # (le glisser complet est consigné au relâchement par _on_click)
        if self._button_down:
            return
        t = time.time()
        dt   = t - self._last_move_time
        dist = ((x - self._last_move_x) ** 2 + (y - self._last_move_y) ** 2) ** 0.5
        if dt < MOVE_THROTTLE_S or dist < MOVE_MIN_DIST_PX:
            return
        self._last_move_time = t
        self._last_move_x    = x
        self._last_move_y    = y
        delay = self._compute_delay(t)
        action = Action(
            index       = self._next_index(),
            action_type = "move",
            timestamp   = t,
            x=x, y=y,
            delay_before=delay,
        )
        with self._lock:
            self.actions.append(action)

    # ── Handlers clavier ──────────────────────────────────────────────────────

    def _on_key_press(self, key):
        if not self.recording:
            return
        t = time.time()

        try:
            # Caractère imprimable → bufferisation
            char = key.char
            if char:
                self._typed_buffer += char
                self._last_key_time = t
                return
        except AttributeError:
            pass

        # Touche spéciale (Enter, Tab, Escape, F-keys…)
        self._flush_typed_buffer()
        key_name = str(key).replace("Key.", "")
        delay = self._compute_delay(t)

        # Enter/Tab valident souvent un champ → on capture le contexte
        visual = None
        if key_name in ("enter", "tab", "escape"):
            cx, cy = pyautogui.position()
            visual = self._capture_visual_context(cx, cy, "key")

        action = Action(
            index       = self._next_index(),
            action_type = "key",
            timestamp   = t,
            key         = key_name,
            visual_context = asdict(visual) if visual else None,
            delay_before   = delay,
            app_name       = get_foreground_app(),
        )
        with self._lock:
            self.actions.append(action)
        log.debug("[%d] Touche: %s", action.index, key_name)

    def _on_key_release(self, key):
        # Flush automatique si pause > 1 s après frappe
        if self._typed_buffer and (time.time() - self._last_key_time) > 1.0:
            self._flush_typed_buffer()

    def _flush_typed_buffer(self):
        if not self._typed_buffer:
            return
        t = self._last_key_time or time.time()
        delay = self._compute_delay(t)
        cx, cy = pyautogui.position()
        visual = self._capture_visual_context(cx, cy, "type")

        action = Action(
            index       = self._next_index(),
            action_type = "type",
            timestamp   = t,
            x=cx, y=cy,
            text        = self._typed_buffer,
            visual_context = asdict(visual) if visual else None,
            delay_before   = delay,
            app_name       = get_foreground_app(),
        )
        with self._lock:
            self.actions.append(action)
        log.info("[%d] Saisie: %r — label: %r — OCR: %r",
                 action.index, self._typed_buffer[:40],
                 visual.label if visual else "",
                 visual.ocr_text[:60] if visual else "")
        self._typed_buffer = ""

    # ── Capture visuelle ──────────────────────────────────────────────────────

    def _capture_visual_context(self, x: int, y: int,
                                action_type: str = "click") -> Optional[VisualContext]:
        """Screenshot de la région autour du point, puis OCR + label."""
        try:
            img, region = screenshot_region(x, y, SCREENSHOT_PADDING)

            if self._reader is not None:
                img_np   = np.array(img)
                results  = self._reader.readtext(img_np, detail=0)
                ocr_text = " | ".join(results).strip()
            else:
                ocr_text = ""   # OCR indisponible : contexte visuel sans texte
            label = derive_label(ocr_text, action_type)

            ctx = VisualContext(
                ocr_text         = ocr_text,
                label            = label,
                screenshot_region= region,
            )

            # Toujours capturer le screenshot (comportement v4)
            import base64, io
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            ctx.screenshot_b64 = base64.b64encode(buf.getvalue()).decode()

            return ctx

        except Exception as e:
            log.warning("Impossible de capturer le contexte visuel : %s", e)
            return None

    # ── Utilitaires ───────────────────────────────────────────────────────────

    def _next_index(self) -> int:
        self._action_index += 1
        return self._action_index

    def _compute_delay(self, t: float) -> float:
        if self._last_timestamp == 0:
            self._last_timestamp = t
            return 0.0
        delay = round(t - self._last_timestamp, 3)
        self._last_timestamp = t
        return delay

    def _save_session(self) -> Path:
        ts   = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        stem = f"scenario_{ts}"
        path = SCENARIOS_DIR / f"{stem}.json"

        with self._lock:
            data = {
                "version":        "3.0",
                "scenario_name":  self._scenario_name or stem,
                "target_app":     self._target_app,
                "recorded_at":    ts,
                "action_count":   len(self.actions),
                "actions":        [asdict(a) for a in self.actions],
            }

        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        return path


# ─── CLI simple ───────────────────────────────────────────────────────────────

def main():
    import sys
    scenario_name = ""
    target_app = ""
    for arg in sys.argv[1:]:
        if arg.startswith("--name="):
            scenario_name = arg.split("=", 1)[1]
        elif arg.startswith("--app="):
            target_app = arg.split("=", 1)[1]
    recorder = ActionRecorder(scenario_name=scenario_name, target_app=target_app)
    recorder.start()
    print("Enregistrement en cours… Appuyez sur ENTRÉE pour arrêter.")
    input()
    session_path = recorder.stop()
    print(f"Scénario sauvegardé : {session_path}")


if __name__ == "__main__":
    main()
