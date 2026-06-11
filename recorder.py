"""
recorder.py — Enregistrement des actions utilisateur (clics + saisies)
avec capture visuelle de la zone cible via EasyOCR.

Sortie : session_YYYYMMDD_HHMMSS.json
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
import easyocr
from PIL import Image
import numpy as np
from pynput import mouse, keyboard

# ─── Configuration ────────────────────────────────────────────────────────────

SESSIONS_DIR = Path("sessions")
SESSIONS_DIR.mkdir(exist_ok=True)

SCREENSHOT_PADDING = 80          # px autour du clic pour la capture visuelle
OCR_LANGUAGES      = ["fr", "en"]
DOUBLE_CLICK_GAP   = 0.3         # secondes max entre deux clics pour détecter un double-clic

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [RECORDER] %(levelname)s — %(message)s"
)
log = logging.getLogger("recorder")

# ─── Structures de données ────────────────────────────────────────────────────

@dataclass
class VisualContext:
    """Texte OCR extrait autour de la zone d'action (ancre visuelle)."""
    ocr_text: str                  # texte détecté dans la zone
    screenshot_region: list        # [x, y, w, h]
    screenshot_b64: Optional[str] = None  # PNG encodé base64 (facultatif)

@dataclass
class Action:
    index:          int
    action_type:    str            # "click" | "double_click" | "right_click" | "type" | "key"
    timestamp:      float          # epoch
    x:              Optional[int]  = None
    y:              Optional[int]  = None
    button:         Optional[str]  = None
    text:           Optional[str]  = None
    key:            Optional[str]  = None
    visual_context: Optional[dict] = None
    delay_before:   float          = 0.0   # délai depuis l'action précédente (s)

# ─── Recorder principal ───────────────────────────────────────────────────────

class ActionRecorder:
    def __init__(self, save_screenshots: bool = False):
        self.save_screenshots = save_screenshots
        self.actions: list[Action] = []
        self.recording = False
        self._lock = threading.Lock()
        self._last_timestamp: float = 0.0
        self._action_index = 0
        self._pending_click: Optional[tuple] = None   # (x, y, button, t)
        self._typed_buffer: str = ""
        self._last_key_time: float = 0.0
        self._mouse_listener  = None
        self._keyboard_listener = None

        log.info("Initialisation EasyOCR (langues : %s)…", OCR_LANGUAGES)
        self._reader = easyocr.Reader(OCR_LANGUAGES, gpu=False, verbose=False)
        log.info("EasyOCR prêt.")

    # ── Contrôle ──────────────────────────────────────────────────────────────

    def start(self):
        self.recording = True
        self.actions.clear()
        self._action_index = 0
        self._last_timestamp = time.time()
        self._typed_buffer = ""

        self._mouse_listener = mouse.Listener(
            on_click=self._on_click
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
        if not self.recording or not pressed:
            return

        t = time.time()
        btn_name = button.name  # "left" | "right" | "middle"

        # Flush la saisie clavier en cours avant tout clic
        self._flush_typed_buffer()

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

        action_type = "right_click" if btn_name == "right" else "click"
        visual = self._capture_visual_context(x, y)
        delay  = self._compute_delay(t)

        action = Action(
            index       = self._next_index(),
            action_type = action_type,
            timestamp   = t,
            x=x, y=y,
            button      = btn_name,
            visual_context = asdict(visual) if visual else None,
            delay_before   = delay,
        )
        with self._lock:
            self.actions.append(action)
        log.info("[%d] %s en (%d, %d) — OCR: %r",
                 action.index, action_type, x, y,
                 visual.ocr_text[:60] if visual else "")

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
            visual = self._capture_visual_context(cx, cy)

        action = Action(
            index       = self._next_index(),
            action_type = "key",
            timestamp   = t,
            key         = key_name,
            visual_context = asdict(visual) if visual else None,
            delay_before   = delay,
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
        visual = self._capture_visual_context(cx, cy)

        action = Action(
            index       = self._next_index(),
            action_type = "type",
            timestamp   = t,
            x=cx, y=cy,
            text        = self._typed_buffer,
            visual_context = asdict(visual) if visual else None,
            delay_before   = delay,
        )
        with self._lock:
            self.actions.append(action)
        log.info("[%d] Saisie: %r — OCR: %r",
                 action.index, self._typed_buffer[:40],
                 visual.ocr_text[:60] if visual else "")
        self._typed_buffer = ""

    # ── Capture visuelle ──────────────────────────────────────────────────────

    def _capture_visual_context(self, x: int, y: int) -> Optional[VisualContext]:
        """Screenshot de la région autour du point, puis OCR."""
        try:
            sw, sh = pyautogui.size()
            rx = max(0, x - SCREENSHOT_PADDING)
            ry = max(0, y - SCREENSHOT_PADDING)
            rw = min(SCREENSHOT_PADDING * 2, sw - rx)
            rh = min(SCREENSHOT_PADDING * 2, sh - ry)

            screenshot = pyautogui.screenshot(region=(rx, ry, rw, rh))
            img_np = np.array(screenshot)

            results = self._reader.readtext(img_np, detail=0)
            ocr_text = " | ".join(results).strip()

            ctx = VisualContext(
                ocr_text         = ocr_text,
                screenshot_region= [rx, ry, rw, rh],
            )

            if self.save_screenshots:
                import base64, io
                buf = io.BytesIO()
                screenshot.save(buf, format="PNG")
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
        path = SESSIONS_DIR / f"session_{ts}.json"

        with self._lock:
            data = {
                "version":    "1.0",
                "recorded_at": ts,
                "action_count": len(self.actions),
                "actions": [asdict(a) for a in self.actions],
            }

        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        return path


# ─── CLI simple ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys

    recorder = ActionRecorder(save_screenshots="--screenshots" in sys.argv)
    recorder.start()

    print("Enregistrement en cours… Appuyez sur ENTRÉE pour arrêter.")
    input()

    session_path = recorder.stop()
    print(f"Session sauvegardée : {session_path}")
