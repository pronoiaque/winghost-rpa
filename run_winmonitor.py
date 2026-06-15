"""
run_winmonitor.py — Point d'entrée packagé (PyInstaller) de la CLI.

PyInstaller analyse ce script comme racine : il tire ainsi tout le package
`winmonitor` + `version.py`. L'exécutable produit est `winmonitor.exe`, qui
expose la même CLI que la commande `winmonitor` (record / replay / schedule…).
"""

import sys

from winmonitor.cli import main

if __name__ == "__main__":
    sys.exit(main())
