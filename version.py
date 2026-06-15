"""
version.py — Source UNIQUE de la version de WinGhost Monitor.

Tout composant affichant un numéro de version (CLI, dashboard, rapport) DOIT
lire `__version__` ici, jamais une chaîne en dur. Le workflow CI vérifie la
cohérence avec `pyproject.toml`.
"""

__version__ = "0.1.0"
