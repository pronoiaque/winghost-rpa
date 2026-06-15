"""
version.py — Source UNIQUE de la version de WinGhost.

Tout ce qui affiche un numéro de version (titre de fenêtre, splash, bandeau,
rapport de débug) DOIT lire `__version__` ici, jamais une chaîne en dur. Le
workflow CI vérifie que `pyproject.toml` est cohérent avec cette valeur, ce qui
empêche définitivement le décalage « binaire v6.4 affichant v6.3 ».

Pour publier une nouvelle version : bumper ICI, mettre à jour CHANGELOG.md /
README.md, committer — le build CI se déclenche tout seul sur push vers main.
"""

__version__ = "6.5.0"
