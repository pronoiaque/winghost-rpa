"""
anchor.py — Ancrage visuel par OpenCV `matchTemplate` (cœur de la Couche 2).

On recherche l'imagette enregistrée (template) dans la capture courante, à
plusieurs échelles (tolérance DPI / compression RDP / AppliDis). Le meilleur
score de corrélation (`TM_CCOEFF_NORMED`, ∈ [-1, 1]) au-dessus du seuil valide
l'ancrage et fournit le point de clic re-localisé.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from winmonitor import config


@dataclass
class AnchorMatch:
    """Résultat d'un ancrage."""
    found: bool
    x: int = 0           # point d'action re-localisé (écran courant)
    y: int = 0
    confidence: float = 0.0
    scale: float = 1.0


def _to_gray(img: np.ndarray) -> np.ndarray:
    import cv2

    if img.ndim == 3:
        return cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    return img


def locate_template(
    screen: np.ndarray,
    template: np.ndarray,
    click_offset: tuple[int, int],
    *,
    confidence: float = config.ANCHOR_CONFIDENCE,
    scales: list[float] | None = None,
) -> AnchorMatch:
    """
    Cherche `template` dans `screen` à plusieurs échelles.

    `click_offset` = position du point d'action relative au coin haut-gauche du
    template (à l'échelle 1.0) ; il est mis à l'échelle du meilleur match pour
    retrouver le point de clic exact sur l'écran courant.
    """
    import cv2

    scales = scales or config.ANCHOR_SCALES
    g_screen = _to_gray(screen)
    g_tpl0 = _to_gray(template)
    sh, sw = g_screen.shape[:2]
    best = AnchorMatch(found=False)

    for scale in scales:
        if scale == 1.0:
            g_tpl = g_tpl0
        else:
            new_w = max(1, int(round(g_tpl0.shape[1] * scale)))
            new_h = max(1, int(round(g_tpl0.shape[0] * scale)))
            interp = cv2.INTER_AREA if scale < 1.0 else cv2.INTER_LINEAR
            g_tpl = cv2.resize(g_tpl0, (new_w, new_h), interpolation=interp)

        th, tw = g_tpl.shape[:2]
        if th > sh or tw > sw:
            continue  # template plus grand que l'écran à cette échelle

        res = cv2.matchTemplate(g_screen, g_tpl, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, max_loc = cv2.minMaxLoc(res)
        if max_val > best.confidence:
            ox, oy = click_offset
            px = int(round(max_loc[0] + ox * scale))
            py = int(round(max_loc[1] + oy * scale))
            best = AnchorMatch(
                found=max_val >= confidence,
                x=px,
                y=py,
                confidence=float(max_val),
                scale=scale,
            )
            # Corrélation quasi-parfaite : inutile d'explorer d'autres échelles.
            if max_val >= 0.99:
                break

    return best
