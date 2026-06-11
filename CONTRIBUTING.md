# Contribuer à WinGhost RPA

Merci de votre intérêt ! Ce guide explique comment proposer des modifications,
signaler des bugs, ou suggérer des évolutions.

---

## Signaler un bug

Ouvrir une **Issue** GitHub avec :

1. **Version Python** (`python --version`)
2. **Version Windows** (10 / 11, 32 / 64 bits)
3. **Commande exécutée** et message d'erreur complet
4. **Étapes pour reproduire** le problème
5. **Comportement attendu** vs **comportement observé**

---

## Proposer une évolution

Ouvrir une **Issue** avec le label `enhancement` avant de commencer à coder —
cela permet de discuter de la pertinence et de l'approche avant d'investir du temps.

---

## Workflow de contribution (Pull Request)

```bash
# 1. Forker le dépôt sur GitHub, puis cloner votre fork
git clone https://github.com/VOTRE_USERNAME/winghost-rpa.git
cd winghost-rpa

# 2. Créer un environnement virtuel
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt

# 3. Créer une branche descriptive
git checkout -b fix/nom-du-bug
# ou
git checkout -b feature/nom-de-la-fonctionnalite

# 4. Faire vos modifications

# 5. Committer avec un message conventionnel
git commit -m "fix: correction du décalage OCR sur écrans 4K"
# ou
git commit -m "feat: export rapport HTML avec graphique SVG"

# 6. Pousser et ouvrir une Pull Request vers main
git push origin fix/nom-du-bug
```

---

## Conventions de commit

Format : `type: description courte en minuscules`

| Préfixe | Usage |
|---|---|
| `feat` | Nouvelle fonctionnalité |
| `fix` | Correction de bug |
| `docs` | Documentation uniquement |
| `refactor` | Restructuration sans changement de comportement |
| `perf` | Amélioration de performance |
| `test` | Ajout ou correction de tests |
| `chore` | Maintenance, dépendances, config |

---

## Style de code

- **PEP 8** — longueur de ligne max 100 caractères
- **Type hints** sur toutes les fonctions publiques
- **Docstrings** en français pour les classes et méthodes publiques
- Les constantes configurables restent en haut du fichier, commentées
- Pas de dépendances supplémentaires sans discussion préalable en Issue

---

## Mettre à jour CHANGELOG.md

Toute modification visible par l'utilisateur doit être documentée dans
`CHANGELOG.md` sous la section `[Non publié]`, dans la catégorie appropriée
(`Ajouté`, `Modifié`, `Corrigé`, `Supprimé`).
