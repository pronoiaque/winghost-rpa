# WinGhost Monitor v0.2 — CHU Toulouse

> **Supervision de la performance applicative** par RPA visuel. Rejoue des
> scénarios métier (RDP, Win32, web/AppliDis) à intervalles réguliers et mesure
> le **temps de réponse réel** des applications du CHU — par plage horaire, avec
> baseline, alertes de régression, **interface graphique Flet** et tableau de
> bord HTML autonome.

![License MIT](https://img.shields.io/badge/license-MIT-blue)
![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue)
![Windows](https://img.shields.io/badge/os-Windows-lightgrey)
![Version](https://img.shields.io/badge/version-0.2.0-orange)

> ℹ️ **Refonte (fork) de WinGhost RPA.** Le code historique d'enregistrement /
> rejeu (v6.x, monolithe Tkinter) reste disponible sur la branche `main`. Ce
> projet repart d'une architecture propre en 4 couches centrée sur la **mesure
> de performance**, et non plus seulement l'automatisation.

---

## Pourquoi cette refonte ?

La v6.x rejouait fidèlement souris **et** clavier, mais le moteur clavier
« hésitait » avant chaque frappe (cascade de backends + forçage de focus) — ce
qui **polluait toute mesure de temps de réponse**.

La parade architecturale : **on ne chronomètre plus l'injection des entrées**.
On mesure le temps que met **l'écran à se stabiliser** après une action
(*chronomètre visuel* : `t_action → écran stable`). C'est la vraie réactivité
de l'application, indépendante de la vitesse du clavier/souris.

---

## Architecture en 4 couches

```
Couche 1 — Recorder        pynput (souris/clavier) + MSS (screenshots) → scénario JSON + ancres visuelles
Couche 2 — Replayer        ancrage OpenCV matchTemplate + adaptateur DPI/RDP + retry/timeout/fallback
Couche 3 — KPI Collector   chronomètre visuel (t_action → écran stable) + store SQLite (UTC) + dashboard HTML
Scheduler                  APScheduler par plage horaire (08h-09h, 12h, 17h…) → agrégation → rapport quotidien
```

| Couche | Module | Rôle |
|---|---|---|
| 1 | `winmonitor/recorder/` | `listener.py` (hooks pynput), `screenshot.py` (MSS), `scenario.py` (modèle JSON + ancres) |
| 2 | `winmonitor/replayer/` | `anchor.py` (matchTemplate multi-échelle), `dpi.py` (facteur d'échelle RDP/DPI), `injector.py` (SendInput rapide), `replayer.py` (orchestration retry/fallback) |
| 3 | `winmonitor/kpi/` | `chrono.py` (chronomètre visuel), `store.py` (SQLite), `baseline.py` (médiane/p95 + régression), `dashboard.py` (HTML/Chart.js) |
| — | `winmonitor/scheduler/` | `runner.py` (APScheduler), `report.py` (rapport quotidien) |

---

## Interface graphique (Flet)

Au **double-clic** sur `winmonitor.exe` (ou via `winmonitor gui`), l'application
ouvre une fenêtre reprenant la logique « magnéto » de la v6.6.0 :

| Bouton | Comportement |
|---|---|
| 🔴 **REC** | Lance l'enregistrement ; bascule en **⏹ STOP REC** (rouge) jusqu'à l'arrêt (bouton ou ÉCHAP) |
| ▶️ **REPLAY** | Rejoue le scénario sélectionné ; bascule en **⏹ STOP** (rouge) puis revient |
| 📝 **RAPPORT** | (Re)génère le dashboard HTML et l'ouvre dans le navigateur |

Le panneau **« Replay live »** décrit chaque action en temps réel (clic, saisie,
touche, déplacement) avec son **temps de réponse visuel**, l'icône d'ancrage
(🔍 template / 📌 absolu) et un statut coloré. La liste des scénarios est un
**accordéon repliable**.

---

## Installation

```bash
pip install -r requirements.txt          # ou : pip install -e .
```

### Exécutable Windows (sans Python)

Pour un déploiement sur poste CHU sans installation Python, un binaire
mono-fichier `winmonitor.exe` est produit par GitHub Actions
(`.github/workflows/build-windows.yml`, PyInstaller sur `windows-latest`) :

- **téléchargeable** comme artefact à chaque push (onglet *Actions*) ;
- **publié en Release** sur tag `v*` (ex. `v0.1.1`).

L'exe embarque Flet (IHM), OpenCV (ancrage visuel), pynput, MSS et APScheduler.
**Sans argument, il ouvre l'interface graphique** ; les sous-commandes CLI
restent disponibles : `winmonitor.exe record|replay|schedule|dashboard|report`.

Build local (sur Windows) :

```powershell
pip install -r requirements-build.txt
pyinstaller --noconfirm --clean winghost-monitor.spec
.\dist\winmonitor.exe --version
```

## Utilisation

```bash
# 1. Enregistrer un scénario (souris/clavier ; ÉCHAP pour terminer)
winmonitor record ouverture_dossier_patient

# 2. Le rejouer une fois et mesurer le temps de réponse
winmonitor replay ouverture_dossier_patient

# 3. Planifier les mesures par plage horaire (+ rapport quotidien à 20h)
winmonitor schedule

# 4. (Re)générer le tableau de bord et le rapport
winmonitor dashboard
winmonitor report 2026-06-15

# Dashboard 100 % hors-ligne : récupérer Chart.js une seule fois
winmonitor fetch-chartjs
```

Les données vivent sous `~/.winghost-monitor/` (surchargé par `WINMONITOR_HOME`) :
`scenarios/`, `metrics.db` (SQLite), `dashboard/index.html`, `reports/`, `fallback/`.

---

## Mesure du temps de réponse (chronomètre visuel)

1. Juste avant de déclencher l'action, on relève `t_action`.
2. On capture l'écran en boucle (toutes les 50 ms).
3. Tant que deux captures diffèrent (diff. moyenne de pixels > seuil), l'appli
   « répond ». Dès que l'écran reste identique sur N images → **stable**.
4. **Temps de réponse = dernier changement − t_action.**

Le seuil de stabilité, l'intervalle de capture et le timeout sont réglables
dans `winmonitor/config.py`.

---

## Robustesse RDP / Win32 / Web

- **Ancrage visuel** (`matchTemplate`) : la cible est re-localisée à partir d'une
  imagette enregistrée, donc insensible aux déplacements de fenêtre.
- **Multi-échelle** : tolère la compression RDP / AppliDis et la mise à l'échelle
  Windows (125 %/150 %).
- **Adaptateur DPI/RDP** : recalcule un facteur d'échelle quand la résolution de
  rejeu diffère de l'enregistrement.
- **Repli + diagnostic** : si l'ancrage échoue, on rejoue sur les coordonnées
  mises à l'échelle et on archive une capture dans `fallback/`.

---

## Licence

MIT — voir [LICENSE](LICENSE).
