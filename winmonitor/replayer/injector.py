"""
injector.py — Injection des entrées souris/clavier (chemin rapide).

Leçon de la v6.x : l'ancien moteur « hésitait » avant chaque frappe à cause
d'une cascade de backends (SendInput → pynput → keyboard → pyautogui) doublée
d'un forçage de focus systématique. Ici on adopte UN chemin rapide :

  • Windows → `SendInput` direct (ctypes), saisie texte en `KEYEVENTF_UNICODE`
    (indépendant de la disposition AZERTY/QWERTY), AUCUN délai artificiel ;
  • hors Windows / SendInput indisponible → repli unique `pyautogui`.

La mesure de performance ne dépend de toute façon PAS de la vitesse d'injection
(cf. chronomètre visuel), mais une injection franche évite de polluer t_action.
"""

from __future__ import annotations

import sys
import time

# ─── Constantes Win32 ─────────────────────────────────────────────────────────
_INPUT_MOUSE = 0
_INPUT_KEYBOARD = 1
_KEYEVENTF_KEYUP = 0x0002
_KEYEVENTF_UNICODE = 0x0004
_MOUSEEVENTF_MOVE_ABS = 0x8001          # MOVE | ABSOLUTE
_MOUSEEVENTF_LEFTDOWN, _MOUSEEVENTF_LEFTUP = 0x0002, 0x0004
_MOUSEEVENTF_RIGHTDOWN, _MOUSEEVENTF_RIGHTUP = 0x0008, 0x0010
_MOUSEEVENTF_MIDDLEDOWN, _MOUSEEVENTF_MIDDLEUP = 0x0020, 0x0040
_MOUSEEVENTF_WHEEL = 0x0800

_IS_WINDOWS = sys.platform.startswith("win")

# Noms pynput/usuels → code de touche virtuelle (VK) Windows.
_VK = {
    "enter": 0x0D, "return": 0x0D, "tab": 0x09, "esc": 0x1B, "escape": 0x1B,
    "space": 0x20, "backspace": 0x08, "delete": 0x2E, "home": 0x24, "end": 0x23,
    "up": 0x26, "down": 0x28, "left": 0x25, "right": 0x27,
    "page_up": 0x21, "page_down": 0x22,
    "f1": 0x70, "f2": 0x71, "f3": 0x72, "f4": 0x73, "f5": 0x74, "f6": 0x75,
    "f7": 0x76, "f8": 0x77, "f9": 0x78, "f10": 0x79, "f11": 0x7A, "f12": 0x7B,
    "ctrl": 0x11, "ctrl_l": 0x11, "ctrl_r": 0x11, "alt": 0x12, "alt_l": 0x12,
    "shift": 0x10, "shift_l": 0x10, "shift_r": 0x10,
}


def _win_structs():
    """Construit (paresseusement) les structures ctypes SendInput."""
    import ctypes
    from ctypes import wintypes

    ULONG_PTR = ctypes.POINTER(ctypes.c_ulong)

    class MOUSEINPUT(ctypes.Structure):
        _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG),
                    ("mouseData", wintypes.DWORD), ("dwFlags", wintypes.DWORD),
                    ("time", wintypes.DWORD), ("dwExtraInfo", ULONG_PTR)]

    class KEYBDINPUT(ctypes.Structure):
        _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD),
                    ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD),
                    ("dwExtraInfo", ULONG_PTR)]

    class _IUNION(ctypes.Union):
        _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT)]

    class INPUT(ctypes.Structure):
        _fields_ = [("type", wintypes.DWORD), ("u", _IUNION)]

    return ctypes, INPUT, MOUSEINPUT, KEYBDINPUT


class Injector:
    """Injecteur d'entrées. `screen_size` sert au calcul des coords absolues Win32."""

    def __init__(self, screen_size: tuple[int, int]) -> None:
        self.screen_w, self.screen_h = screen_size
        self.backend = "win32" if _IS_WINDOWS else "pyautogui"

    # ─── Souris ────────────────────────────────────────────────────────────────
    def move(self, x: int, y: int) -> None:
        if self.backend == "win32":
            self._win_mouse(x, y, _MOUSEEVENTF_MOVE_ABS)
        else:
            self._pyautogui().moveTo(x, y)

    def click(self, x: int, y: int, button: str = "left", double: bool = False) -> None:
        if self.backend == "win32":
            down, up = {
                "left": (_MOUSEEVENTF_LEFTDOWN, _MOUSEEVENTF_LEFTUP),
                "right": (_MOUSEEVENTF_RIGHTDOWN, _MOUSEEVENTF_RIGHTUP),
                "middle": (_MOUSEEVENTF_MIDDLEDOWN, _MOUSEEVENTF_MIDDLEUP),
            }.get(button, (_MOUSEEVENTF_LEFTDOWN, _MOUSEEVENTF_LEFTUP))
            self._win_mouse(x, y, _MOUSEEVENTF_MOVE_ABS)
            for _ in range(2 if double else 1):
                self._win_mouse(x, y, down)
                self._win_mouse(x, y, up)
        else:
            pg = self._pyautogui()
            pg.click(x=x, y=y, button=button, clicks=2 if double else 1)

    def scroll(self, x: int, y: int, dy: int) -> None:
        if self.backend == "win32":
            self._win_mouse(x, y, _MOUSEEVENTF_MOVE_ABS)
            self._win_mouse(x, y, _MOUSEEVENTF_WHEEL, mouse_data=dy * 120)
        else:
            self._pyautogui().scroll(dy, x=x, y=y)

    # ─── Clavier ───────────────────────────────────────────────────────────────
    def type_text(self, text: str) -> None:
        """Saisie d'une chaîne en Unicode (chemin rapide, sans délai artificiel)."""
        if self.backend == "win32":
            for ch in text:
                self._win_unicode(ch)
        else:
            self._pyautogui().typewrite(text, interval=0)

    def press_key(self, name: str) -> None:
        name = (name or "").lower().lstrip("key.")
        if self.backend == "win32":
            vk = _VK.get(name)
            if vk is not None:
                self._win_vk(vk)
            elif len(name) == 1:
                self._win_unicode(name)
        else:
            try:
                self._pyautogui().press(name)
            except Exception:
                pass

    # ─── Implémentations Win32 ─────────────────────────────────────────────────
    def _win_mouse(self, x, y, flags, mouse_data=0):
        ctypes, INPUT, MOUSEINPUT, _ = _win_structs()
        # Coordonnées absolues normalisées sur 0..65535.
        ax = int(x * 65535 / max(1, self.screen_w - 1))
        ay = int(y * 65535 / max(1, self.screen_h - 1))
        mi = MOUSEINPUT(ax, ay, mouse_data & 0xFFFFFFFF, flags, 0, None)
        inp = INPUT(type=_INPUT_MOUSE)
        inp.u.mi = mi
        ctypes.windll.user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(inp))

    def _win_unicode(self, ch):
        ctypes, INPUT, _, KEYBDINPUT = _win_structs()
        code = ord(ch)
        for flags in (_KEYEVENTF_UNICODE, _KEYEVENTF_UNICODE | _KEYEVENTF_KEYUP):
            ki = KEYBDINPUT(0, code, flags, 0, None)
            inp = INPUT(type=_INPUT_KEYBOARD)
            inp.u.ki = ki
            ctypes.windll.user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(inp))

    def _win_vk(self, vk):
        ctypes, INPUT, _, KEYBDINPUT = _win_structs()
        for flags in (0, _KEYEVENTF_KEYUP):
            ki = KEYBDINPUT(vk, 0, flags, 0, None)
            inp = INPUT(type=_INPUT_KEYBOARD)
            inp.u.ki = ki
            ctypes.windll.user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(inp))

    @staticmethod
    def _pyautogui():
        import pyautogui

        pyautogui.PAUSE = 0          # pas de pause implicite (clé du « non-hésitant »)
        pyautogui.FAILSAFE = False
        return pyautogui
