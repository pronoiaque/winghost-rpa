@echo off
:: ─────────────────────────────────────────────────────────────────────────────
:: winghost.bat — Lanceur WinGhost RPA
:: Double-cliquer pour ouvrir l'interface graphique.
:: ─────────────────────────────────────────────────────────────────────────────

setlocal

:: Cherche Python dans le venv local, sinon dans le PATH système
if exist "%~dp0.venv\Scripts\python.exe" (
    set PYTHON="%~dp0.venv\Scripts\python.exe"
) else (
    set PYTHON=python
)

echo.
echo  ________________________________________________________
echo  ^|                                                      ^|
echo  ^|   WinGhost RPA — demarrage...                        ^|
echo  ^|   Fermer cette fenetre pour quitter l'application.   ^|
echo  ^|______________________________________________________^|
echo.

%PYTHON% "%~dp0gui.py"

if errorlevel 1 (
    echo.
    echo  ERREUR : Python ou les dependances sont manquantes.
    echo  Executer : pip install -r requirements.txt
    echo.
    pause
)
