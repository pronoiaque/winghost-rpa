# WinGhost RPA — Instructions Claude Code

## Règle systématique : tout push doit mettre à jour CHANGELOG.md et README.md

À chaque commit/push vers le dépôt, **sans exception** :

1. **`version.py`** — SOURCE UNIQUE de la version : bumper `__version__ = "X.Y.Z"`.
   L'IHM (titre, splash, bandeau) et le débug lisent cette valeur — ne JAMAIS
   remettre un numéro de version en dur dans `gui.py`.

2. **CHANGELOG.md** — ajouter une section `## [X.Y.Z] — YYYY-MM-DD` avec :
   - Sous-sections claires (### Ajouté / Modifié / Corrigé)
   - Description des changements en français
   - Détails techniques si pertinents

3. **README.md** — mettre à jour :
   - Le numéro de version dans le titre et le badge `![Version]`
   - La section « Nouveautés vX.Y » si c'est une nouvelle version mineure/majeure
   - Toute documentation affectée par les changements

4. **pyproject.toml** — bumper `version = "X.Y.Z"` (DOIT être identique à
   `version.py`, sinon le build CI échoue sur l'étape de cohérence).

Ces quatre fichiers doivent **toujours être inclus dans le même commit** que les
modifications de code.

## Build automatique du binaire

Le workflow `.github/workflows/build-windows.yml` se déclenche **automatiquement
à chaque push sur `main`** et produit l'artefact `WinGhost-windows-x64`
(WinGhost.exe). Il n'y a donc rien à faire manuellement : pousser sur `main`
suffit. Un tag `v*` publie en plus une Release GitHub avec l'exe attaché.

Workflow de release type :
1. Bumper `version.py` + `pyproject.toml`, MAJ `CHANGELOG.md` + `README.md`
2. Commit + push sur la branche de dev, puis fast-forward `main`
3. Le build se lance tout seul → récupérer l'exe dans l'onglet Actions

## Branche de développement

Développement sur `claude/exciting-noether-8bqv7r`, push via :
```
git push -u origin claude/exciting-noether-8bqv7r
```

## Conventions de commit

Format : `type(scope): description courte`
- `feat(vX.Y)` — nouvelle fonctionnalité
- `fix(vX.Y)` — correction de bug
- `build` — packaging, CI, spec PyInstaller
- `docs` — documentation seule
