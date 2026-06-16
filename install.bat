@echo off
:: ─────────────────────────────────────────────────────────────────────────────
:: install.bat — Installation automatique de WinGhost RPA
:: ─────────────────────────────────────────────────────────────────────────────

setlocal
cd /d "%~dp0"

echo.
echo  ________________________________________________________
echo  ^|   WinGhost RPA — Installation                        ^|
echo  ^|______________________________________________________^|
echo.

:: Vérifier Python
python --version >nul 2>&1
if errorlevel 1 (
    echo  [ERREUR] Python n'est pas installe ou pas dans le PATH.
    echo  Telecharger Python 3.10+ sur https://www.python.org/downloads/
    pause
    exit /b 1
)

echo  [OK] Python detecte :
python --version
echo.

:: Créer l'environnement virtuel
if not exist ".venv" (
    echo  Creation de l'environnement virtuel...
    python -m venv .venv
    if errorlevel 1 (
        echo  [ERREUR] Impossible de creer le venv.
        pause
        exit /b 1
    )
    echo  [OK] Environnement virtuel cree.
) else (
    echo  [OK] Environnement virtuel existant detecte.
)

echo.

:: Activer et installer
echo  Installation des dependances (peut prendre quelques minutes)...
call .venv\Scripts\activate
pip install --upgrade pip --quiet
pip install -r requirements.txt

if errorlevel 1 (
    echo.
    echo  [ERREUR] L'installation des dependances a echoue.
    echo  Verifier votre connexion internet et relancer install.bat.
    pause
    exit /b 1
)

echo.
echo  ________________________________________________________
echo  ^|   Installation terminee avec succes !                ^|
echo  ^|                                                      ^|
echo  ^|   Double-cliquer sur winghost.bat pour demarrer.     ^|
echo  ^|______________________________________________________^|
echo.

pause
