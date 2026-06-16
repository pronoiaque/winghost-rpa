"""
screenshot.py — Capture d'écran rapide (MSS) renvoyée en image OpenCV (BGR).

MSS est privilégié (capture quasi-instantanée, multi-moniteurs). Repli sur
Pillow/`mss` absent → `PIL.ImageGrab`. Le grabber expose une interface unique
utilisée par le recorder (imagettes d'ancrage) ET par le chronomètre visuel
(détection de stabilité), pour garantir des pixels homogènes des deux côtés.
"""

from __future__ import annotations

import numpy as np


class ScreenGrabber:
    """Capture d'écran réutilisable. Garde une instance MSS ouverte (perf)."""

    def __init__(self) -> None:
        self._sct = None
        self._backend = None
        self._init_backend()

    def _init_backend(self) -> None:
        try:
            import mss  # import paresseux : absent sur l'environnement de build CI

            self._sct = mss.mss()
            self._backend = "mss"
        except Exception:
            self._backend = "pil"

    # ─── API publique ────────────────────────────────────────────────────────
    def grab(self, region: tuple[int, int, int, int] | None = None) -> np.ndarray:
        """
        Capture l'écran (ou une région [x, y, w, h]) et renvoie un tableau
        numpy BGR (compatible OpenCV). `region` None = écran principal entier.
        """
        if self._backend == "mss":
            return self._grab_mss(region)
        return self._grab_pil(region)

    def screen_size(self) -> tuple[int, int]:
        """Résolution (W, H) de l'écran principal."""
        if self._backend == "mss":
            mon = self._sct.monitors[1]
            return mon["width"], mon["height"]
        from PIL import ImageGrab

        img = ImageGrab.grab()
        return img.size

    # ─── Backends ────────────────────────────────────────────────────────────
    def _grab_mss(self, region):
        if region is None:
            mon = self._sct.monitors[1]
        else:
            x, y, w, h = region
            mon = {"left": x, "top": y, "width": w, "height": h}
        raw = self._sct.grab(mon)
        # mss renvoie du BGRA → on retire le canal alpha.
        arr = np.asarray(raw)[:, :, :3]
        return np.ascontiguousarray(arr)

    def _grab_pil(self, region):
        from PIL import ImageGrab

        if region is None:
            img = ImageGrab.grab()
        else:
            x, y, w, h = region
            img = ImageGrab.grab(bbox=(x, y, x + w, y + h))
        # PIL = RGB → OpenCV attend du BGR.
        return np.asarray(img)[:, :, ::-1].copy()

    def close(self) -> None:
        if self._sct is not None:
            try:
                self._sct.close()
            except Exception:
                pass
            self._sct = None
