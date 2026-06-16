# -*- mode: python ; coding: utf-8 -*-
"""
winghost.spec — Recette PyInstaller pour produire un binaire Windows x64 unique.

Build LÉGER (v6.6) : EasyOCR / PyTorch sont SUPPRIMÉS définitivement.
La localisation dynamique s'appuie sur OpenCV (template matching multi-échelle)
embarqué dans le binaire via `locator.py`.

Compilation (sur Windows x64 uniquement — PyInstaller ne cross-compile pas) :
    pip install pyinstaller
    pyinstaller --noconfirm winghost.spec
    => dist/WinGhost.exe
"""

from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

block_cipher = None
PROJECT = Path(SPECPATH)

# ─── Données embarquées (lecture seule) ──────────────────────────────────────
datas = []
for asset in ("logo_chu.png", "logo_chu.svg"):
    p = PROJECT / "assets" / asset
    if p.exists():
        datas.append((str(p), "assets"))

# CustomTkinter embarque ses thèmes / assets sous forme de fichiers de données.
datas += collect_data_files("customtkinter")

# ─── Imports masqués (non détectés par l'analyse statique) ────────────────────
hiddenimports = [
    "win32gui", "win32process", "win32api", "win32con",
    "psutil", "pystray._win32", "PIL._tkinter_finder",
    # Modules importés paresseusement (dans des fonctions) → forcés ici.
    "winput", "dev_debug", "version", "trace_log", "keyboard",
    # Localisation dynamique template matching (v6.6)
    "locator", "cv2",
]
hiddenimports += collect_submodules("flask")

# ─── Modules lourds explicitement exclus (binaire léger) ──────────────────────
excludes = [
    "torch", "torchvision", "torchaudio",
    "easyocr", "scipy", "skimage", "scikit-image",
    "matplotlib", "pandas", "IPython", "notebook", "jupyter",
    "pytest", "test", "tkinter.test",
]

# ─── Icône (.ico) : générée depuis le PNG si Pillow est disponible ────────────
icon_path = PROJECT / "assets" / "logo_chu.ico"
if not icon_path.exists():
    try:
        from PIL import Image
        png = PROJECT / "assets" / "logo_chu.png"
        if png.exists():
            img = Image.open(png).convert("RGBA")
            img.save(icon_path, sizes=[(16, 16), (32, 32), (48, 48),
                                       (64, 64), (128, 128), (256, 256)])
    except Exception:
        icon_path = None
icon = str(icon_path) if icon_path and Path(icon_path).exists() else None


a = Analysis(
    ["gui.py"],
    pathex=[str(PROJECT)],
    binaries=[],
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
    name="WinGhost",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,          # application fenêtrée (pas de console)
    disable_windowed_traceback=False,
    target_arch="x86_64",   # binaire 64 bits
    codesign_identity=None,
    entitlements_file=None,
    icon=icon,
)
