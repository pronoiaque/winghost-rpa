"""
listener.py — Hooks pynput (souris + clavier) → construit un `Scenario`.

Avant CHAQUE action de clic, une imagette (« anchor ») est capturée autour du
point cliqué : c'est elle qui permettra à la Couche 2 de re-localiser la cible
au rejeu. Les frappes imprimables sont regroupées en une saisie texte unique
(`type == "text"`) ; les touches spéciales (Entrée, Tab, F-keys…) sont des
actions `key` distinctes.

NB : pynput nécessite une session graphique. Sur l'environnement de build CI
(headless) le module s'importe sans erreur mais `Recorder.start()` lèvera —
c'est attendu : l'enregistrement se fait sur le poste Windows.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from winmonitor.recorder.scenario import Action, Anchor, Scenario

# Demi-dimensions de l'imagette d'ancrage capturée autour du clic.
_ANCHOR_HALF_W = 60
_ANCHOR_HALF_H = 30


def _save_png(img_bgr: np.ndarray, path: Path) -> None:
    """Écrit un tableau BGR en PNG (OpenCV si dispo, sinon Pillow)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        import cv2

        cv2.imwrite(str(path), img_bgr)
        return
    except Exception:
        from PIL import Image

        Image.fromarray(img_bgr[:, :, ::-1]).save(path)  # BGR → RGB


class Recorder:
    """Enregistre souris + clavier en un `Scenario`. Arrêt via touche ÉCHAP."""

    def __init__(self, name: str, grabber=None) -> None:
        from winmonitor.recorder.screenshot import ScreenGrabber

        self.name = name
        self.grabber = grabber or ScreenGrabber()
        self._actions: list[Action] = []
        self._text_buffer: list[str] = []
        self._last_t: float | None = None
        self._mouse_listener = None
        self._kbd_listener = None
        self._running = False
        w, h = self.grabber.screen_size()
        self._screen_size = [w, h]

    # ─── Cadence ──────────────────────────────────────────────────────────────
    def _delta(self) -> float:
        now = time.perf_counter()
        d = 0.0 if self._last_t is None else max(0.0, now - self._last_t)
        self._last_t = now
        return d

    def _next_index(self) -> int:
        return len(self._actions)

    # ─── Capture d'ancrage ────────────────────────────────────────────────────
    def _capture_anchor(self, x: int, y: int) -> Anchor | None:
        W, H = self._screen_size
        x0 = max(0, x - _ANCHOR_HALF_W)
        y0 = max(0, y - _ANCHOR_HALF_H)
        w = min(W - x0, _ANCHOR_HALF_W * 2)
        h = min(H - y0, _ANCHOR_HALF_H * 2)
        if w <= 0 or h <= 0:
            return None
        try:
            patch = self.grabber.grab((x0, y0, w, h))
        except Exception:
            return None
        idx = self._next_index()
        rel = f"anchors/{idx:03d}.png"
        folder = Scenario.folder_for(self._scenarios_dir, self.name)
        _save_png(patch, folder / rel)
        return Anchor(
            template=rel,
            region=[x0, y0, w, h],
            click_offset=[x - x0, y - y0],
            screen_size=[W, H],
        )

    # ─── Vidage du tampon clavier ─────────────────────────────────────────────
    def _flush_text(self) -> None:
        if not self._text_buffer:
            return
        text = "".join(self._text_buffer)
        self._text_buffer.clear()
        self._actions.append(
            Action(index=self._next_index(), type="text", delta=self._delta(), text=text)
        )

    # ─── Callbacks souris ─────────────────────────────────────────────────────
    def _on_click(self, x, y, button, pressed):
        if not pressed:
            return
        self._flush_text()
        anchor = self._capture_anchor(int(x), int(y))
        self._actions.append(
            Action(
                index=self._next_index(),
                type="click",
                delta=self._delta(),
                x=int(x),
                y=int(y),
                button=getattr(button, "name", "left"),
                anchor=anchor,
            )
        )

    def _on_scroll(self, x, y, dx, dy):
        self._flush_text()
        self._actions.append(
            Action(
                index=self._next_index(),
                type="scroll",
                delta=self._delta(),
                x=int(x),
                y=int(y),
                scroll_dx=int(dx),
                scroll_dy=int(dy),
            )
        )

    # ─── Callbacks clavier ────────────────────────────────────────────────────
    def _on_press(self, key):
        from pynput import keyboard

        if key == keyboard.Key.esc:
            self.stop()
            return False  # interrompt le listener clavier

        char = getattr(key, "char", None)
        if char is not None:
            self._text_buffer.append(char)
        else:
            # Touche spéciale : on vide le texte courant puis on enregistre la touche.
            self._flush_text()
            name = getattr(key, "name", str(key))
            self._actions.append(
                Action(index=self._next_index(), type="key", delta=self._delta(), key=name)
            )

    # ─── Cycle de vie ─────────────────────────────────────────────────────────
    def start(self, scenarios_dir: Path) -> None:
        """Démarre la capture (bloquant jusqu'à ÉCHAP)."""
        from pynput import keyboard, mouse

        self._scenarios_dir = Path(scenarios_dir)
        Scenario.folder_for(self._scenarios_dir, self.name).mkdir(parents=True, exist_ok=True)
        self._running = True
        self._last_t = time.perf_counter()

        self._mouse_listener = mouse.Listener(
            on_click=self._on_click, on_scroll=self._on_scroll
        )
        self._kbd_listener = keyboard.Listener(on_press=self._on_press)
        self._mouse_listener.start()
        self._kbd_listener.start()
        self._kbd_listener.join()   # bloque jusqu'à ÉCHAP
        self.stop()

    def stop(self) -> None:
        if not self._running:
            return
        self._running = False
        self._flush_text()
        for lst in (self._mouse_listener, self._kbd_listener):
            try:
                if lst is not None:
                    lst.stop()
            except Exception:
                pass

    def build_scenario(self) -> Scenario:
        return Scenario(
            name=self.name,
            created_at=datetime.now(timezone.utc).isoformat(),
            screen_size=self._screen_size,
            actions=list(self._actions),
        )

    def save(self, scenarios_dir: Path) -> Path:
        return self.build_scenario().save(scenarios_dir)
