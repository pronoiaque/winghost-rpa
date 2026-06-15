# WinGhost RPA — Instructions Claude Code

## Règle systématique : tout push doit mettre à jour CHANGELOG.md et README.md

À chaque commit/push vers le dépôt, **sans exception** :

1. **CHANGELOG.md** — ajouter une section `## [X.Y.Z] — YYYY-MM-DD` avec :
   - Sous-sections claires (### Ajouté / Modifié / Corrigé)
   - Description des changements en français
   - Détails techniques si pertinents

2. **README.md** — mettre à jour :
   - Le numéro de version dans le titre et le badge `![Version]`
   - La section « Nouveautés vX.Y » si c'est une nouvelle version mineure/majeure
   - Toute documentation affectée par les changements

3. **pyproject.toml** — bumper `version = "X.Y.Z"` en cohérence avec le CHANGELOG.

Ces trois fichiers doivent **toujours être inclus dans le même commit** que les modifications de code.

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
