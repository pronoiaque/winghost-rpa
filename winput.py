"""
winput.py — Précision des entrées Windows (souris + clavier) et horloge haute
résolution. Centralise les correctifs de fidélité enregistrement/rejeu (v6.4).

Trois problèmes historiques traités ici :

1. DÉRIVE DE LA SOURIS
   pynput enregistre des pixels PHYSIQUES ; pyautogui (non « DPI-aware ») rejoue
   dans un espace de coordonnées VIRTUALISÉ dès que la mise à l'échelle de
   l'affichage ≠ 100 % (125 %/150 % par défaut sous Windows). L'écart croît avec
   la distance à l'origine → « dérive ». `enable_dpi_awareness()` aligne les deux
   espaces en rendant le processus per-monitor DPI-aware AVANT tout clic/capture.

2. TOUCHES JAMAIS TAPÉES
   `pyautogui.typewrite()` ignore SILENCIEUSEMENT tout caractère absent de son jeu
   ASCII : c'est le cas de TOUS les accents français (é è à ç ù…), de l'€, etc.
   `type_text()` utilise `pynput.keyboard.Controller` (injection Unicode native
   sous Windows) et compte les caractères réellement émis pour vérification.

3. HORLOGE
   `time.time()` a une granularité d'environ 15 ms sous Windows. `now()` repose
   sur `time.perf_counter()` (sous-microseconde) pour des délais fidèles à la ms.

Le module ne lève jamais d'exception à l'import et se dégrade proprement hors
Windows / si pynput est absent.
"""

from __future__ import annotations

import sys
import time
import logging

log = logging.getLogger("winput")

# ─── Clavier pynput (injection Unicode fiable) ────────────────────────────────
try:
    from pynput.keyboard import Controller as _KbController, Key as _Key
    _kb = _KbController()
    _HAS_PYNPUT = True
except Exception:                                   # pragma: no cover
    _kb = None
    _Key = None
    _HAS_PYNPUT = False

# pyautogui sert de repli (touches spéciales surtout)
try:
    import pyautogui
except Exception:                                   # pragma: no cover
    pyautogui = None


# ─── 1. Conscience DPI (corrige la dérive de la souris) ───────────────────────

_dpi_done = False


def enable_dpi_awareness() -> bool:
    """
    Rend le processus per-monitor DPI-aware afin que pynput (enregistrement,
    pixels physiques) et pyautogui (rejeu) partagent le MÊME repère de
    coordonnées. À appeler une fois, au plus tôt, sur chaque point d'entrée
    (GUI, recorder CLI, replayer CLI, scheduler).

    Renvoie True si la conscience DPI a été activée, False sinon (autre OS,
    appel trop tardif, API indisponible). Idempotent et sans exception.
    """
    global _dpi_done
    if _dpi_done:
        return True
    if not sys.platform.startswith("win"):
        _dpi_done = True
        return False

    import ctypes

    # API moderne (Windows 10 1703+) : PER_MONITOR_AWARE_V2 = -4
    try:
        ctx = ctypes.c_void_p(-4)
        if ctypes.windll.user32.SetProcessDpiAwarenessContext(ctx):
            _dpi_done = True
            log.info("DPI : per-monitor v2 activé.")
            return True
    except Exception:
        pass

    # Repli (Windows 8.1+) : PROCESS_PER_MONITOR_DPI_AWARE = 2
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
        _dpi_done = True
        log.info("DPI : per-monitor (shcore) activé.")
        return True
    except Exception:
        pass

    # Repli historique (Vista+) : System-DPI aware
    try:
        ctypes.windll.user32.SetProcessDPIAware()
        _dpi_done = True
        log.info("DPI : system-aware activé (repli).")
        return True
    except Exception:
        log.warning("DPI : impossible d'activer la conscience DPI.")
        return False


# ─── 2. Horloge haute résolution ──────────────────────────────────────────────

def now() -> float:
    """Horloge monotone haute résolution (s, sous-microseconde). Pour les délais."""
    return time.perf_counter()


# ─── 3. Saisie clavier fiable (Unicode) ───────────────────────────────────────

def type_text(text: str, interval: float = 0.012) -> tuple[int, int]:
    """
    Tape `text` caractère par caractère de façon fiable, accents compris.

    Utilise pynput (injection Unicode native sous Windows) en priorité, avec
    repli pyautogui par caractère. Renvoie (n_emis, n_total) pour permettre une
    vérification dans les journaux : si n_emis < n_total, des caractères ont été
    refusés par la cible.
    """
    if not text:
        return (0, 0)

    total = len(text)
    sent = 0
    for ch in text:
        ok = False
        if _HAS_PYNPUT:
            try:
                _kb.type(ch)                # gère é è à ç €… via Unicode
                ok = True
            except Exception:
                ok = False
        if not ok and pyautogui is not None:
            try:
                pyautogui.write(ch)         # repli ASCII
                ok = True
            except Exception:
                ok = False
        if ok:
            sent += 1
        if interval:
            time.sleep(interval)

    if sent < total:
        log.warning("Saisie partielle : %d/%d caractères émis pour %r",
                    sent, total, text[:40])
    return (sent, total)


# ─── 4. Touches spéciales fiables ─────────────────────────────────────────────

# Noms pynput (issus du recorder, ex. "enter", "shift_l") → touche pynput.
_PYNPUT_KEYS = {
    "enter": "enter", "return": "enter", "tab": "tab", "esc": "esc",
    "escape": "esc", "space": "space", "backspace": "backspace",
    "delete": "delete", "insert": "insert",
    "up": "up", "down": "down", "left": "left", "right": "right",
    "home": "home", "end": "end", "page_up": "page_up", "page_down": "page_down",
    "caps_lock": "caps_lock", "num_lock": "num_lock",
    "shift": "shift", "shift_l": "shift", "shift_r": "shift_r",
    "ctrl": "ctrl", "ctrl_l": "ctrl_l", "ctrl_r": "ctrl_r",
    "alt": "alt", "alt_l": "alt_l", "alt_r": "alt_gr", "alt_gr": "alt_gr",
    "cmd": "cmd", "cmd_l": "cmd", "cmd_r": "cmd",
    **{f"f{i}": f"f{i}" for i in range(1, 21)},
    "media_volume_up": "media_volume_up",
    "media_volume_down": "media_volume_down",
}

# Repli pyautogui : noms recorder → noms pyautogui.
_PYAUTOGUI_KEYS = {
    "enter": "enter", "return": "enter", "tab": "tab", "escape": "esc",
    "esc": "esc", "space": "space", "backspace": "backspace",
    "delete": "delete", "insert": "insert",
    "up": "up", "down": "down", "left": "left", "right": "right",
    "home": "home", "end": "end", "page_up": "pageup", "page_down": "pagedown",
    "caps_lock": "capslock", "num_lock": "numlock",
    "shift": "shift", "shift_l": "shift", "shift_r": "shift",
    "ctrl": "ctrl", "ctrl_l": "ctrl", "ctrl_r": "ctrl",
    "alt": "alt", "alt_l": "alt", "alt_r": "altright", "alt_gr": "altright",
    **{f"f{i}": f"f{i}" for i in range(1, 13)},
}


def press_key(name: str) -> bool:
    """
    Presse une touche spéciale par son nom recorder (ex. "enter", "tab",
    "page_up"). Renvoie True si l'émission a réussi. pynput d'abord (fidèle aux
    noms enregistrés), repli pyautogui sinon.
    """
    if not name:
        return False

    if _HAS_PYNPUT:
        pk = _PYNPUT_KEYS.get(name)
        if pk is not None:
            try:
                key_obj = getattr(_Key, pk, None)
                if key_obj is not None:
                    _kb.press(key_obj)
                    _kb.release(key_obj)
                    return True
            except Exception:
                pass

    if pyautogui is not None:
        pg = _PYAUTOGUI_KEYS.get(name, name)
        try:
            pyautogui.press(pg)
            return True
        except Exception:
            return False
    return False
