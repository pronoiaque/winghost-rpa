"""
dev_debug.py — Diagnostic « Débug dev » (v6.4).

Rassemble TOUT ce qui ne peut être testé hors Windows et qui explique
pourquoi une saisie clavier rejouée peut n'aboutir à AUCUN caractère :

  • Disposition clavier active (AZERTY français ⇒ pyautogui brouille/abandonne
    les caractères ; seule l'injection Unicode SendInput/pynput est fiable).
  • Élévation : si l'application cible tourne en ADMINISTRATEUR et pas WinGhost,
    Windows (UIPI) bloque SILENCIEUSEMENT toute frappe synthétique.
  • Conscience DPI / mise à l'échelle (dérive de la souris).
  • Moteurs d'injection disponibles + code de retour réel de SendInput.
  • Auto-test de frappe : on tape une chaîne connue dans un champ et on relit
    ce qui est réellement arrivé.
  • Inspection d'un scénario : combien d'actions « type » / « key », quel texte,
    champs vides éventuels.

Toutes les sondes sont défensives : aucune ne lève d'exception.
"""

from __future__ import annotations

import json
import platform
import sys
from datetime import datetime
from pathlib import Path

# Chaîne d'auto-test : lettres, MAJ, chiffres, accents, symboles, espace.
TYPING_TEST_STRING = "azAZ09 éèàçù €&é\"'(-è_"


def _safe(fn, default="(indisponible)"):
    try:
        return fn()
    except Exception as e:                          # pragma: no cover
        return f"(erreur: {e})"


# ─── Sondes Windows ───────────────────────────────────────────────────────────

def _is_windows() -> bool:
    return sys.platform.startswith("win")


def keyboard_layout() -> str:
    """Disposition clavier active (HKL) + interprétation FR/US."""
    if not _is_windows():
        return "n/a (hors Windows)"
    import ctypes
    user32 = ctypes.windll.user32
    hwnd = user32.GetForegroundWindow()
    tid = user32.GetWindowThreadProcessId(hwnd, 0)
    hkl = user32.GetKeyboardLayout(tid)
    langid = hkl & 0xFFFF
    known = {
        0x040C: "Français (France) — AZERTY",
        0x080C: "Français (Belgique) — AZERTY",
        0x0C0C: "Français (Canada)",
        0x0409: "Anglais (US) — QWERTY",
        0x0809: "Anglais (RU) — QWERTY",
    }
    name = known.get(langid, f"langid=0x{langid:04X}")
    flag = ""
    if langid in (0x040C, 0x080C):
        flag = "  ⚠ AZERTY : pyautogui brouille/abandonne les caractères → " \
               "injection Unicode (SendInput) indispensable."
    return f"0x{hkl:08X} → {name}{flag}"


def is_admin() -> str:
    if not _is_windows():
        return "n/a"
    import ctypes
    try:
        return "OUI" if ctypes.windll.shell32.IsUserAnAdmin() else "NON"
    except Exception:
        return "(inconnu)"


def integrity_level() -> str:
    """Niveau d'intégrité du processus courant (High = élevé/admin)."""
    if not _is_windows():
        return "n/a"
    import ctypes
    from ctypes import wintypes
    try:
        # v6.4.1 : signatures ctypes EXPLICITES. Sans elles, le pseudo-handle
        # 64 bits de GetCurrentProcess() est tronqué (ctypes suppose c_int),
        # OpenProcessToken échoue → « token inaccessible ».
        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        adv = ctypes.WinDLL("advapi32", use_last_error=True)
        k32.GetCurrentProcess.restype = wintypes.HANDLE
        adv.OpenProcessToken.argtypes = [wintypes.HANDLE, wintypes.DWORD,
                                         ctypes.POINTER(wintypes.HANDLE)]
        adv.OpenProcessToken.restype = wintypes.BOOL
        adv.GetTokenInformation.argtypes = [wintypes.HANDLE, ctypes.c_int,
                                            ctypes.c_void_p, wintypes.DWORD,
                                            ctypes.POINTER(wintypes.DWORD)]
        adv.GetTokenInformation.restype = wintypes.BOOL
        adv.GetSidSubAuthorityCount.argtypes = [ctypes.c_void_p]
        adv.GetSidSubAuthorityCount.restype = ctypes.POINTER(ctypes.c_ubyte)
        adv.GetSidSubAuthority.argtypes = [ctypes.c_void_p, wintypes.DWORD]
        adv.GetSidSubAuthority.restype = ctypes.POINTER(wintypes.DWORD)

        TOKEN_QUERY = 0x0008
        TokenIntegrityLevel = 25

        class SID_AND_ATTRIBUTES(ctypes.Structure):
            _fields_ = [("Sid", ctypes.c_void_p), ("Attributes", wintypes.DWORD)]

        class TOKEN_MANDATORY_LABEL(ctypes.Structure):
            _fields_ = [("Label", SID_AND_ATTRIBUTES)]

        htok = wintypes.HANDLE()
        if not adv.OpenProcessToken(k32.GetCurrentProcess(), TOKEN_QUERY,
                                    ctypes.byref(htok)):
            return f"(token inaccessible, err={ctypes.get_last_error()})"
        try:
            size = wintypes.DWORD()
            adv.GetTokenInformation(htok, TokenIntegrityLevel, None, 0,
                                    ctypes.byref(size))
            buf = ctypes.create_string_buffer(size.value)
            if not adv.GetTokenInformation(htok, TokenIntegrityLevel, buf, size,
                                           ctypes.byref(size)):
                return f"(lecture échouée, err={ctypes.get_last_error()})"
            tml = ctypes.cast(buf, ctypes.POINTER(TOKEN_MANDATORY_LABEL)).contents
            sid = tml.Label.Sid
            count = adv.GetSidSubAuthorityCount(sid).contents.value
            rid = adv.GetSidSubAuthority(sid, count - 1).contents.value
        finally:
            k32.CloseHandle(htok)
        levels = {0x0000: "Untrusted", 0x1000: "Low", 0x2000: "Medium",
                  0x2100: "Medium+", 0x3000: "High", 0x4000: "System"}
        return levels.get(rid, f"0x{rid:04X}")
    except Exception as e:
        return f"(erreur: {e})"


def foreground_window() -> str:
    if not _is_windows():
        return "n/a"
    import ctypes
    try:
        import win32gui, win32process, psutil
        hwnd = win32gui.GetForegroundWindow()
        title = win32gui.GetWindowText(hwnd)
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        proc = psutil.Process(pid).name()
        return f"{proc} (pid={pid}) — « {title} »"
    except Exception as e:
        return f"(erreur: {e})"


def dpi_state() -> str:
    if not _is_windows():
        return "n/a"
    import ctypes
    try:
        import winput
        aware = winput._dpi_done
        dpi = ctypes.windll.user32.GetDpiForSystem()
        scale = round(dpi / 96 * 100)
        return (f"conscience DPI activée={aware} ; DPI système={dpi} "
                f"(échelle {scale} %)"
                + ("" if scale == 100 else
                   "  ⚠ échelle ≠ 100 % : sans conscience DPI la souris dérive."))
    except Exception as e:
        return f"(erreur: {e})"


def sendinput_probe() -> str:
    """Teste un appel SendInput Unicode réel et renvoie son code de retour."""
    try:
        import winput
        if not winput._HAS_SENDINPUT:
            return "SendInput indisponible (non Windows ou ctypes KO)"
        ok, n, err = winput._sendinput_unicode_char(chr(0x200B))  # espace large nul (invisible)
        if ok:
            return "SendInput OK (2 événements insérés)"
        return (f"SendInput a inséré {n}/2 événements, GetLastError={err} "
                f"⚠ blocage probable (UIPI / privilèges).")
    except Exception as e:
        return f"(erreur: {e})"


def backends() -> str:
    try:
        import winput
        parts = [
            f"prioritaire = {winput.active_typing_backend()}",
            f"SendInput={winput._HAS_SENDINPUT}",
            f"pynput={winput._HAS_PYNPUT}",
            f"pyautogui={winput.pyautogui is not None}",
        ]
        return " ; ".join(parts)
    except Exception as e:
        return f"(erreur: {e})"


def versions() -> str:
    import importlib.metadata as md
    # Nom d'import → nom de distribution (pour importlib.metadata).
    dist = {"PIL": "Pillow"}
    out = []
    for mod in ("pyautogui", "pynput", "numpy", "PIL", "customtkinter"):
        ver = None
        try:
            m = __import__(mod)
            ver = getattr(m, "__version__", None)
        except Exception:
            out.append(f"{mod}=absent")
            continue
        if not ver:
            # pynput n'expose pas __version__ → on lit les métadonnées du paquet.
            try:
                ver = md.version(dist.get(mod, mod))
            except Exception:
                ver = "?"
        out.append(f"{mod}={ver}")
    return " ; ".join(out)


# ─── Inspection d'un scénario ─────────────────────────────────────────────────

def inspect_scenario(path: Path) -> str:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception as e:
        return f"Lecture impossible de {path} : {e}"

    actions = data.get("actions", [])
    by_type: dict[str, int] = {}
    for a in actions:
        by_type[a.get("action_type", "?")] = by_type.get(a.get("action_type", "?"), 0) + 1

    lines = [f"Scénario : {Path(path).name}",
             f"  Actions totales : {len(actions)}",
             f"  Répartition : {by_type}"]

    type_actions = [a for a in actions if a.get("action_type") == "type"]
    key_actions = [a for a in actions if a.get("action_type") == "key"]
    lines.append(f"  Actions « type » : {len(type_actions)} ; « key » : {len(key_actions)}")

    if not type_actions and not key_actions:
        lines.append("  ⚠ AUCUNE action clavier enregistrée — rien à rejouer côté "
                     "saisie (problème à l'ENREGISTREMENT, pas au rejeu).")

    empties = [a for a in type_actions if not (a.get("text") or "")]
    if empties:
        lines.append(f"  ⚠ {len(empties)} action(s) « type » avec texte VIDE.")

    for a in type_actions[:10]:
        txt = a.get("text") or ""
        lines.append(f"    type #{a.get('index')} (x={a.get('x')},y={a.get('y')}) "
                     f"len={len(txt)} text={txt!r}")
    for a in key_actions[:10]:
        lines.append(f"    key  #{a.get('index')} key={a.get('key')!r}")
    return "\n".join(lines)


# ─── Rapport global ────────────────────────────────────────────────────────────

def environment_report() -> str:
    try:
        from version import __version__ as _ver
    except Exception:
        _ver = "?"
    L = []
    L.append(f"══════════ WinGhost — Rapport de débug dev (v{_ver}) ══════════")
    L.append(f"Date            : {datetime.now().isoformat(timespec='seconds')}")
    L.append(f"OS              : {platform.platform()}")
    L.append(f"Python          : {sys.version.split()[0]} ({platform.machine()})")
    L.append(f"Gelé (frozen)   : {getattr(sys, 'frozen', False)}")
    L.append(f"Bibliothèques   : {versions()}")
    L.append("")
    L.append("─── Saisie clavier (cause n°1 des caractères non rejoués) ───")
    L.append(f"Disposition     : {keyboard_layout()}")
    L.append(f"Moteurs         : {backends()}")
    L.append(f"Sonde SendInput : {sendinput_probe()}")
    L.append("")
    L.append("─── Privilèges (UIPI bloque la frappe si la cible est élevée) ───")
    L.append(f"WinGhost admin  : {is_admin()}")
    L.append(f"Intégrité proc. : {integrity_level()}")
    L.append(f"Fenêtre active  : {foreground_window()}")
    L.append("  ↳ Si la fenêtre active est en intégrité 'High'/admin et que "
             "WinGhost est 'Medium', AUCUNE frappe ne passera : relancer "
             "WinGhost en tant qu'administrateur.")
    L.append("")
    L.append("─── Souris / affichage ───")
    L.append(f"DPI             : {dpi_state()}")
    L.append("════════════════════════════════════════════════════════════")
    return "\n".join(L)


def interpret_self_test(expected: str, got: str) -> str:
    """Compare la chaîne attendue à ce qui est réellement arrivé dans le champ."""
    if got == expected:
        return f"✔ Auto-test RÉUSSI : {len(got)}/{len(expected)} caractères identiques."
    if not got:
        return ("✘ Auto-test ÉCHEC TOTAL : 0 caractère reçu. "
                "Causes probables : blocage UIPI (cible élevée) ou aucun moteur "
                "d'injection disponible (voir Sonde SendInput / Moteurs).")
    return (f"⚠ Auto-test PARTIEL : reçu {len(got)} car. au lieu de {len(expected)}.\n"
            f"   attendu : {expected!r}\n   reçu    : {got!r}\n"
            "   Un écart de CONTENU (lettres permutées) trahit un brouillage "
            "QWERTY/AZERTY → l'injection Unicode doit être prioritaire.")


def save_report(text: str) -> Path:
    """Écrit le rapport dans le dossier de données et renvoie le chemin."""
    from paths import data_dir
    d = data_dir() / "debug"
    d.mkdir(parents=True, exist_ok=True)
    p = d / f"winghost_debug_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    p.write_text(text, encoding="utf-8")
    return p
