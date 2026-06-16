"""
locator.py — Cascade de localisation dynamique pour WinGhost RPA v6.6+

Remplace EasyOCR (vérification OCR de contexte) par une cascade :
  1. Template matching OpenCV multi-échelle — relocalisation visuelle pixel
  2. Repli : coordonnées absolues enregistrées

Conçu pour RDP/AppliDis, Win32 natif et navigateurs : tous ces contextes
livrent les pixels rendus côté client → le matching fonctionne sans API
propre au protocole de transport.

Phase 2 (à venir) : slot UI Automation (Win32/web) branché dans la même
cascade sans rien casser dans le contrat de l'appelant.
"""

import base64
import io
import logging
from dataclasses import dataclass
from typing import Optional, Tuple

import numpy as np
import pyautogui
from PIL import Image

log = logging.getLogger("locator")

# ─── Backends optionnels ──────────────────────────────────────────────────────

_HAS_CV2 = False
try:
    import cv2  # opencv-python-headless ou opencv-python
    _HAS_CV2 = True
except ImportError:
    log.warning("OpenCV absent — template matching indisponible, repli coordonnées absolues")

_HAS_WIN32 = False
try:
    import win32gui
    _HAS_WIN32 = True
except ImportError:
    pass

# ─── Configuration ────────────────────────────────────────────────────────────

DEFAULT_CONFIDENCE = 0.75

# Plage d'échelles testées au matching (couvre RDP compressé, DPI 100→150 %)
_SCALES = [1.0, 0.95, 1.05, 0.90, 1.10, 0.85, 1.15, 0.80, 1.20]

# Padding autour de la position enregistrée pour la zone de recherche rapide (px)
_SEARCH_PAD = 400


# ─── Résultat de localisation ─────────────────────────────────────────────────

@dataclass
class LocateResult:
    x: int
    y: int
    confidence: float       # 0..1  (0 = repli absolu)
    method: str             # "template" | "absolute"
    scale: float = 1.0      # échelle retenue (1.0 = identique)


# ─── Helpers internes ─────────────────────────────────────────────────────────

def _pil_to_gray(img: Image.Image) -> np.ndarray:
    return np.array(img.convert("L"))


def _b64_to_pil(b64: str) -> Optional[Image.Image]:
    try:
        return Image.open(io.BytesIO(base64.b64decode(b64))).convert("RGB")
    except Exception:
        return None


def _screenshot_region(x: int, y: int, w: int, h: int) -> Image.Image:
    sw, sh = pyautogui.size()
    rx = max(0, min(x, sw - 1))
    ry = max(0, min(y, sh - 1))
    rw = min(w, sw - rx)
    rh = min(h, sh - ry)
    if rw <= 0 or rh <= 0:
        return pyautogui.screenshot()
    return pyautogui.screenshot(region=(rx, ry, rw, rh))


# ─── Template matching ────────────────────────────────────────────────────────

def _match_template(
    screen_gray: np.ndarray,
    tmpl_gray_orig: np.ndarray,
    offset_x: int,
    offset_y: int,
    click_in_tmpl_x: int,
    click_in_tmpl_y: int,
    confidence: float,
) -> Optional[LocateResult]:
    """
    Essaie de trouver `tmpl_gray_orig` dans `screen_gray` à plusieurs échelles.
    Retourne les coordonnées absolues du centre du click si confiance >= seuil.
    """
    th_orig, tw_orig = tmpl_gray_orig.shape[:2]
    sh, sw = screen_gray.shape[:2]

    best_val = -1.0
    best_loc: Optional[Tuple[int, int]] = None
    best_scale = 1.0

    for scale in _SCALES:
        tw = max(1, int(tw_orig * scale))
        th = max(1, int(th_orig * scale))
        if tw > sw or th > sh:
            continue

        tmpl = cv2.resize(tmpl_gray_orig, (tw, th), interpolation=cv2.INTER_AREA)
        res = cv2.matchTemplate(screen_gray, tmpl, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, max_loc = cv2.minMaxLoc(res)

        if max_val > best_val:
            best_val = max_val
            best_loc = max_loc
            best_scale = scale

    if best_val < confidence or best_loc is None:
        log.debug("Template matching : %.3f < seuil %.2f", best_val, confidence)
        return None

    # Position absolue du clic dans le patch mis à l'échelle
    cx = offset_x + best_loc[0] + int(click_in_tmpl_x * best_scale)
    cy = offset_y + best_loc[1] + int(click_in_tmpl_y * best_scale)

    log.info("Template match ✔ — conf=%.3f scale=%.2f → (%d, %d)", best_val, best_scale, cx, cy)
    return LocateResult(x=cx, y=cy, confidence=best_val,
                        method="template", scale=best_scale)


def _try_template(
    template_b64: str,
    recorded_x: int,
    recorded_y: int,
    recorded_region: Optional[list],
    confidence: float,
    search_region: Optional[Tuple[int, int, int, int]],
) -> Optional[LocateResult]:
    """Tente le matching dans `search_region` (None = plein écran)."""
    tmpl_pil = _b64_to_pil(template_b64)
    if tmpl_pil is None:
        return None

    if search_region:
        sx, sy, sw, sh = search_region
        screen_img = _screenshot_region(sx, sy, sw, sh)
        offset_x, offset_y = sx, sy
    else:
        screen_img = pyautogui.screenshot()
        offset_x, offset_y = 0, 0

    screen_gray = _pil_to_gray(screen_img)
    tmpl_gray   = _pil_to_gray(tmpl_pil)
    th, tw = tmpl_gray.shape[:2]

    # Offset du clic dans le patch original
    if recorded_region and tw > 0 and th > 0:
        click_in_tmpl_x = recorded_x - recorded_region[0]
        click_in_tmpl_y = recorded_y - recorded_region[1]
        # clamper dans les limites du patch
        click_in_tmpl_x = max(0, min(tw - 1, click_in_tmpl_x))
        click_in_tmpl_y = max(0, min(th - 1, click_in_tmpl_y))
    else:
        click_in_tmpl_x = tw // 2
        click_in_tmpl_y = th // 2

    return _match_template(
        screen_gray, tmpl_gray,
        offset_x, offset_y,
        click_in_tmpl_x, click_in_tmpl_y,
        confidence,
    )


# ─── Slot UI Automation (Phase 2) ─────────────────────────────────────────────

def _try_uia(action: dict, confidence: float) -> Optional[LocateResult]:
    """
    Placeholder Phase 2 — UI Automation (Win32 / navigateur).
    Retourne None jusqu'à l'implémentation.
    """
    return None


# ─── API publique ─────────────────────────────────────────────────────────────

def locate(
    action: dict,
    confidence: float = DEFAULT_CONFIDENCE,
) -> LocateResult:
    """
    Cascade de localisation pour une action enregistrée.

    1. Template matching OpenCV (rapide, zone locale puis plein écran)
    2. UI Automation — slot Phase 2, désactivé pour l'instant
    3. Repli coordonnées absolues enregistrées

    Retourne toujours un LocateResult (jamais None).
    Journalise la méthode et la confiance pour affichage dans le journal live.

    Args:
        action : dict d'une action du scénario JSON
        confidence : seuil de corrélation minimum (0..1), config via GUI

    Returns:
        LocateResult.method = "template" | "uia" | "absolute"
    """
    recorded_x: int = action.get("x") or 0
    recorded_y: int = action.get("y") or 0
    visual_ctx: dict = action.get("visual_context") or {}

    # Template = screenshot_b64 de la zone capturée à l'enregistrement
    template_b64: Optional[str] = (
        visual_ctx.get("template_b64")
        or visual_ctx.get("screenshot_b64")
    )
    recorded_region: Optional[list] = visual_ctx.get("screenshot_region")

    if template_b64 and _HAS_CV2:
        sw, sh = pyautogui.size()

        # 1a — zone locale autour de la position connue (rapide)
        lx = max(0, recorded_x - _SEARCH_PAD)
        ly = max(0, recorded_y - _SEARCH_PAD)
        lw = min(sw, recorded_x + _SEARCH_PAD) - lx
        lh = min(sh, recorded_y + _SEARCH_PAD) - ly
        if lw > 0 and lh > 0:
            result = _try_template(
                template_b64, recorded_x, recorded_y, recorded_region,
                confidence, (lx, ly, lw, lh),
            )
            if result:
                return result

        # 1b — plein écran (fenêtre peut avoir bougé)
        result = _try_template(
            template_b64, recorded_x, recorded_y, recorded_region,
            confidence, None,
        )
        if result:
            return result

        log.warning(
            "Localisation : template non trouvé (conf < %.2f) pour action %s "
            "en (%d, %d) — repli coordonnées absolues",
            confidence, action.get("action_type"), recorded_x, recorded_y,
        )

    # 2 — UI Automation (Phase 2 — actuellement no-op)
    uia = _try_uia(action, confidence)
    if uia:
        return uia

    # 3 — Repli absolu
    return LocateResult(x=recorded_x, y=recorded_y, confidence=0.0, method="absolute")


def is_available() -> bool:
    """True si au moins un moteur de localisation dynamique est disponible."""
    return _HAS_CV2
