"""
dpi.py — Adaptateur DPI / RDP : facteur d'échelle par cible.

Quand l'écran de rejeu diffère de l'écran d'enregistrement (résolution RDP,
mise à l'échelle Windows 125 %/150 %, fenêtre AppliDis redimensionnée), les
coordonnées absolues enregistrées ne tombent plus juste. Cet adaptateur :

  • calcule le facteur d'échelle global (courant / enregistré) ;
  • met à l'échelle un point absolu (repli quand l'ancrage visuel échoue) ;
  • propose des échelles de recherche centrées sur ce facteur pour aider
    `matchTemplate` à retrouver l'imagette plus vite.
"""

from __future__ import annotations

from dataclasses import dataclass

from winmonitor import config


@dataclass
class DpiAdapter:
    recorded_size: tuple[int, int]   # (W, H) à l'enregistrement
    current_size: tuple[int, int]    # (W, H) au rejeu

    @property
    def sx(self) -> float:
        rw = self.recorded_size[0] or self.current_size[0] or 1
        return self.current_size[0] / rw

    @property
    def sy(self) -> float:
        rh = self.recorded_size[1] or self.current_size[1] or 1
        return self.current_size[1] / rh

    def scale_point(self, x: int, y: int) -> tuple[int, int]:
        """Met un point absolu enregistré à l'échelle de l'écran courant."""
        return int(round(x * self.sx)), int(round(y * self.sy))

    def search_scales(self) -> list[float]:
        """
        Échelles `matchTemplate` ordonnées autour du facteur DPI estimé.
        On garde la liste par défaut en repli pour couvrir les cas atypiques.
        """
        base = round((self.sx + self.sy) / 2.0, 3)
        scales = [base]
        for s in config.ANCHOR_SCALES:
            cand = round(base * s, 3)
            if cand not in scales and 0.3 <= cand <= 3.0:
                scales.append(cand)
        return scales
