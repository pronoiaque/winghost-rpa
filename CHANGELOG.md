# Changelog — WinGhost Monitor

Toutes les modifications notables sont documentées ici.
Format : [Keep a Changelog](https://keepachangelog.com/fr/1.1.0/) — versionnage [SemVer](https://semver.org/lang/fr/).

> **Note de fork.** WinGhost Monitor est une refonte de WinGhost RPA (v6.x). Le
> changelog du monolithe historique reste consultable sur la branche `main`.

---

## [0.1.1] — 2026-06-15

### Ajouté — Build Windows (exécutable mono-fichier)

- **`winghost-monitor.spec`** : recette PyInstaller produisant `dist/winmonitor.exe`,
  la CLI packagée. OpenCV est désormais **embarqué** (ancrage visuel obligatoire,
  contrairement au build « léger » v6.x) via `opencv-python-headless`
- **`run_winmonitor.py`** : point d'entrée packagé (tire `winmonitor` + `version.py`)
- **`.github/workflows/build-windows.yml`** : build sur `windows-latest` à chaque
  push (`main`, `redesign/**`) et à la demande ; **Release** attachée sur tag `v*` ;
  smoke test `winmonitor.exe --version`
- **`requirements-build.txt`** : dépendances de packaging (toutes les couches +
  `pyinstaller`)

---

## [0.1.0] — 2026-06-15

### Ajouté — Refonte complète « table rase » en 4 couches

Nouvelle architecture orientée **supervision de performance applicative**,
calquée sur le diagramme de conception. Le code monolithique v6.x (Tkinter,
recorder/replayer/locator/scheduler dispersés) est retiré de cette branche.

#### 🏗️ Couche 1 — Recorder (`winmonitor/recorder/`)
- `listener.py` : hooks **pynput** souris + clavier ; les frappes imprimables
  sont regroupées en saisies texte, les touches spéciales restent distinctes
- `screenshot.py` : capture rapide **MSS** (repli Pillow), renvoyée en image
  OpenCV (BGR) — pixels homogènes entre enregistrement et chrono
- `scenario.py` : modèle JSON `Scenario`/`Action`/`Anchor` (tempo + ancre visuelle)

#### 🎯 Couche 2 — Replayer (`winmonitor/replayer/`)
- `anchor.py` : ancrage visuel **OpenCV `matchTemplate`** multi-échelle (TM_CCOEFF_NORMED)
- `dpi.py` : adaptateur **DPI/RDP** (facteur d'échelle + échelles de recherche centrées)
- `injector.py` : injection **chemin rapide** — `SendInput` Windows (clavier en
  `KEYEVENTF_UNICODE`, indépendant AZERTY/QWERTY), **sans délai artificiel**
  (corrige l'« hésitation » clavier de la v6.x) ; repli `pyautogui` unique
- `replayer.py` : orchestration **retry + timeout + fallback** (coordonnées mises
  à l'échelle + screenshot de diagnostic si l'ancrage échoue)

#### 📊 Couche 3 — KPI Collector (`winmonitor/kpi/`)
- `chrono.py` : **chronomètre visuel** `t_action → écran stable` — la mesure ne
  dépend plus de la vitesse d'injection des entrées
- `store.py` : **SQLite** horodaté UTC (tables `runs` + `action_metrics`),
  plage horaire dérivée
- `baseline.py` : médiane / p95 par scénario et par plage + détection de régression
- `dashboard.py` : **tableau de bord HTML autonome** (Chart.js, repli SVG si
  hors-ligne) ; `fetch_chartjs.py` pour un déploiement 100 % hors-ligne

#### ⏰ Scheduler (`winmonitor/scheduler/`)
- `runner.py` : **APScheduler** — un déclenchement par scénario et par plage horaire
- `report.py` : **rapport quotidien** agrégé (HTML + Markdown)

#### 🧰 Outillage
- CLI unique `winmonitor` (record / replay / list / schedule / dashboard / report / fetch-chartjs)
- Test de fumée de la chaîne KPI sans IHM (`tests/test_smoke.py`)
- `version.py` source unique ; CI de cohérence de version conservée
