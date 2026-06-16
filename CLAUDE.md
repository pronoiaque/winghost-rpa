# WinGhost Monitor — Instructions Claude Code

> Refonte (fork) de WinGhost RPA. Architecture en 4 couches centrée sur la
> **mesure de performance applicative** (cf. README). Le monolithe v6.x reste
> sur `main`.

## Règle systématique : tout push met à jour les 4 fichiers de version

À chaque commit/push, **sans exception** :

1. **`version.py`** — SOURCE UNIQUE de la version : bumper `__version__ = "X.Y.Z"`.
2. **CHANGELOG.md** — ajouter une section `## [X.Y.Z] — YYYY-MM-DD` (Ajouté /
   Modifié / Corrigé, en français).
3. **README.md** — mettre à jour le badge `![Version]` et la doc affectée.
4. **pyproject.toml** — bumper `version = "X.Y.Z"` (DOIT être identique à
   `version.py`, sinon la CI échoue sur `tools/check_version.py`).

Ces quatre fichiers doivent **toujours être dans le même commit** que le code.

## Architecture (ne pas mélanger les couches)

```
winmonitor/
  recorder/   Couche 1 — pynput + MSS → scénario JSON + ancres visuelles
  replayer/   Couche 2 — matchTemplate OpenCV + DPI/RDP + injection + retry/fallback
  kpi/        Couche 3 — chronomètre visuel + SQLite + baseline + dashboard
  scheduler/  APScheduler par plage horaire → rapport quotidien
  cli.py      point d'entrée unique `winmonitor`
```

Principe directeur : **la mesure de perf = chronomètre visuel** (`t_action →
écran stable`), jamais le temps d'injection des entrées.

## Conventions

- Constantes/seuils/chemins centralisés dans `winmonitor/config.py` (pas de
  valeur magique dispersée).
- Imports lourds (cv2, pynput, mss, apscheduler) **paresseux** dans les fonctions
  quand un import au niveau module empêcherait l'exécution headless.
- Tests sans IHM dans `tests/` (doivent passer sur Linux CI sans écran/OpenCV).

## Branche de développement

Développement sur `redesign/kpi-monitor`, push via :
```
git push -u origin redesign/kpi-monitor
```

## Format de commit

`type(scope): description courte`
- `feat(couche1|couche2|couche3|scheduler)` — fonctionnalité
- `fix(...)` — correction · `docs` — doc seule · `build` — CI/packaging · `test`
