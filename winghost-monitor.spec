# -*- mode: python ; coding: utf-8 -*-
"""
winghost-monitor.spec — Binaire Windows x64 mono-fichier (PyInstaller).

Produit dist/winmonitor.exe : l'application WinGhost Monitor. Sans argument,
elle ouvre l'INTERFACE GRAPHIQUE Flet ; les sous-commandes CLI restent
disponibles (record / replay / schedule / dashboard / report).

Embarque toutes les couches : Flet (IHM), OpenCV (ancrage visuel, OBLIGATOIRE
ici), pynput (capture), MSS (screenshots), APScheduler (planification),
pywin32 (injection SendInput / contexte fenêtre).

Compilation (sur Windows x64 uniquement — PyInstaller ne cross-compile pas) :
    pip install -r requirements-build.txt
    pyinstaller --noconfirm --clean winghost-monitor.spec
    => dist/winmonitor.exe
"""

from pathlib import Path

from PyInstaller.utils.hooks import collect_all, collect_submodules

block_cipher = None
PROJECT = Path(SPECPATH)

# ─── Imports masqués (non vus par l'analyse statique : imports paresseux) ─────
hiddenimports = [
    "version",
    "win32api", "win32con", "win32gui", "win32process",
    "numpy", "cv2", "mss", "PIL",
]
# Paquets à imports dynamiques internes → on collecte leurs sous-modules.
for pkg in ("apscheduler", "pynput", "mss", "pyautogui"):
    hiddenimports += collect_submodules(pkg)

# Flet (IHM) embarque un client desktop + des données → collecte complète.
datas = []
binaries = []
for pkg in ("flet", "flet_desktop"):
    try:
        d, b, h = collect_all(pkg)
        datas += d
        binaries += b
        hiddenimports += h
    except Exception:
        pass

# ─── Modules lourds/inutiles exclus (binaire plus compact) ────────────────────
excludes = [
    "matplotlib", "pandas", "scipy", "IPython", "notebook", "jupyter",
    "pytest", "torch", "torchvision", "easyocr",
]

a = Analysis(
    ["run_winmonitor.py"],
    pathex=[str(PROJECT)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=excludes,
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="winmonitor",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,           # appli fenêtrée (GUI Flet) → pas de console DOS
    disable_windowed_traceback=False,
    target_arch="x86_64",
    codesign_identity=None,
    entitlements_file=None,
)
