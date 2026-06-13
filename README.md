# WinGhost RPA v6.3 — CHU Toulouse

> Enregistreur / Rejoueur RPA Windows **aux couleurs du CHU de Toulouse**, avec ancrage visuel OCR **optionnel**, capture de tous les inputs souris (clics, molette, glisser), enregistrement des mouvements, splash screen de démarrage, mode automatique planifié (systray), scénarios nommés, log officiel CSV, screenshots systématiques, dashboard web dynamique et interface CustomTkinter moderne.

![License MIT](https://img.shields.io/badge/license-MIT-blue)
![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue)
![Windows](https://img.shields.io/badge/os-Windows-lightgrey)
![Version](https://img.shields.io/badge/version-6.3.0-green)

---

## Nouveautés v6.3

| Fonctionnalité | Description |
|---|---|
| 🔓 **Vérification visuelle OCR optionnelle** | Le rejeu conditionné à l'OCR (« ne rejouer que si le contexte visuel correspond ») devient une **option décochée par défaut** : case **« Vérifier le contexte visuel (OCR) »** dans *Options replay* |
| ⚡ **Rejeu direct par défaut** | Sans la case cochée, **toutes les actions sont rejouées sans contrôle OCR** → plus rapide, plus robuste, plus de clics « sautés ». EasyOCR n'est pas sollicité ; le seuil OCR est grisé tant que l'option est décochée |

---

## Nouveautés v6.2

| Fonctionnalité | Description |
|---|---|
| 🎨 **Thème clair CHU Toulouse** | Interface claire institutionnelle : bleu CHU `#0091CE`, vert `#8BC53F`, texte ardoise `#1E2A38`, fonds blanc / `#EDF2F8` — bandeau supérieur bleu CHU |
| 🐚 **Logo coquille CHU** | Logo « coquille Saint-Jacques » en dégradé bleu→vert (`chu_logo.py` + `assets/logo_chu.svg`), affiché dans l'en-tête, le splash, l'icône de fenêtre et le systray |

> ⚠️ Le logo est une **reconstruction libre** inspirée de l'identité du CHU de Toulouse (la charte officielle n'ayant pu être récupérée automatiquement). Pour un usage officiel, remplacez `assets/logo_chu.svg` / `assets/logo_chu.png` par le fichier de la direction de la communication ; la palette est ajustable dans `chu_logo.COLORS` et l'en-tête de `gui.py`.

---

## Nouveautés v6.1

| Fonctionnalité | Description |
|---|---|
| 🖱️ **Tous les inputs souris** | Le recorder capture désormais le **clic milieu** (`middle_click`), la **molette** (`scroll`) et le **glisser-déposer** (`drag`) — en plus des clics gauche/droit, double-clics et mouvements |
| 🐛 **Clics rejoués de façon fiable** | Correction du symptôme « la souris bouge mais ne clique pas » : seuil OCR par défaut abaissé à **0.25** (était 0.40) pour éviter les faux négatifs qui faisaient sauter les clics, tout en conservant le gate OCR strict |

---

## Nouveautés v6

| Fonctionnalité | Description |
|---|---|
| 🖱️ **Mouvements souris enregistrés** | Le recorder consigne désormais les déplacements du curseur (action `move`), throttlés (10 FPS max, 15 px min) pour un rejeu fidèle de la trajectoire |
| 🎯 **Rejeu conditionné à l'OCR** | Les clics et saisies ne sont rejoués **que si** le contexte visuel correspond (score OCR ≥ seuil) ; les `move` sont exécutés directement, sans vérification |
| ⏳ **Splash screen de démarrage** | Écran d'accueil avec barre de progression pendant le chargement d'EasyOCR (long à initialiser) — la fenêtre principale n'apparaît qu'une fois prêt |
| ♻️ **Lecteur OCR partagé** | EasyOCR n'est initialisé qu'**une seule fois** au démarrage puis réutilisé par le recorder et le replayer (gain de temps notable) |

---

## Nouveautés v5

| Fonctionnalité | Description |
|---|---|
| 🔁 **Mode automatique** | Rejoue un scénario en boucle à intervalle régulier (**30 min par défaut**) — répond à la spec « tourner toutes les 30 mins » |
| 📥 **Réduction en systray** | Pendant l'automatique, la fenêtre se réduit dans la zone de notification ; un clic sur l'icône la restaure |
| 🚨 **Alerte sur échec** | Gros popup rouge plein écran dès qu'un cycle se solde par un `ÉCHEC`, avec le détail des actions fautives |
| 🎯 **Application cible** | Champ texte où l'on saisit le nom de l'application visée — inscrit tel quel dans le journal officiel |
| ⏱️ **Deux métriques de temps** | Dashboard : **bout-en-bout** (horloge réelle) **et applicatif cumulé** (réactivité pure), chacune avec une bulle d'aide explicative |

---

## Nouveautés v4

| Fonctionnalité | Description |
|---|---|
| 🎨 **Interface CustomTkinter** | UI moderne et arrondie remplaçant Tkinter — thème dark cohérent, bulles d'aide (tooltips) sur tous les contrôles |
| 🗂️ **Gestion des scénarios** | Renommer, supprimer directement depuis la liste — fichiers sauvegardés dans `scenarios/` |
| 📋 **Log officiel CSV** | Fichiers mensuels `logs/official_YYYYMM.csv` : application, scénario, date, durée, statut |
| 🪵 **Log debug séparé** | Journal technique (actions, OCR, erreurs) accessible via sous-onglet — log officiel affiché en premier plan |
| 📸 **Screenshots systématiques** | Capture 160 px autour de chaque clic/saisie, toujours active — plus d'option à cocher |
| 🖥️ **Nom d'application capturé** | Processus Windows en premier plan enregistré pour chaque action (via pywin32 / psutil) |
| 📊 **Stats temps réel** | Onglet Stats long-terme corrigé : actualisation automatique après replay et au changement d'onglet |

---

## Fonctionnement

### 1. Enregistrement (`recorder.py`)

L'outil écoute **tous les inputs** souris et clavier via **pynput** : clics gauche / droit / **milieu**, double-clics, **molette** (`scroll`), **glisser-déposer** (`drag`), déplacements du curseur (`move`, throttlé à 10 FPS / 15 px) et saisies clavier. À chaque clic ou saisie :

1. Capture du **nom de l'application** active (processus Windows via pywin32 + psutil)
2. Screenshot de la région autour du curseur (±160 px, multi-moniteurs)
3. Reconnaissance OCR (EasyOCR, fr + en) — déduction d'un **label humain** (`"Connexion"`, `"Champ mot de passe"`)
4. Sauvegarde dans `scenarios/scenario_YYYYMMDD_HHMMSS.json` (v3.0, rétrocompatible v1/v2)

> EasyOCR est initialisé **une seule fois** au démarrage (pendant le splash screen) puis partagé entre le recorder et le replayer.

### 2. Replay simple (`ActionReplayer`)

Pour chaque action enregistrée :

1. **Vérification OCR — optionnelle (v6.3, décochée par défaut)** : si la case **« Vérifier le contexte visuel (OCR) »** est cochée, le contexte visuel actuel est comparé à celui enregistré (score `difflib`) et l'action est ignorée si le score est sous le seuil. **Par défaut (case décochée), cette étape est ignorée** et toutes les actions sont rejouées
2. **Exécution** via PyAutoGUI (les `move` sont rejoués directement via `moveTo`, sans vérification ni mesure de réponse)
3. **Screenshot post-action** : PNG base64 de la région (160 px) autour du clic — toujours capturé
4. **Mesure du temps de réponse** : polling pixel-à-pixel jusqu'au prochain changement d'écran

> 💡 **Quand activer le gate OCR ?** Cochez la case si l'interface cible peut bouger entre l'enregistrement et le rejeu (fenêtres déplacées, contenu dynamique) et que vous voulez éviter de cliquer « à l'aveugle ». Laissez-la décochée pour un rejeu rapide et déterministe sur une interface stable (cas le plus courant).

### 3. Multi-run (`MultiReplayRunner`)

Lance N fois la même session, avec pause configurable entre les runs. Chaque run est :
- persisté individuellement en base SQLite (`winghost_stats.db`)
- consigné dans le log officiel CSV (`logs/official_YYYYMM.csv`)

Cela permet d'analyser :
- La **tendance** du temps de réponse au fil des runs
- Les **pics de lag** par heure de la journée (heatmap horaire)
- Le **taux de succès** par bouton/label sur la durée

### 4. Log officiel

Chaque replay (simple ou multi) ajoute une entrée dans `logs/official_YYYYMM.csv` :

```
app_name;scenario_name;execution_date;duration_s;status;ok_count;total_count;run_id
MonApp;Connexion admin;2026-06-12T14:32:00;8.3;SUCCÈS;12;12;42
```

| Statut | Critère |
|---|---|
| `SUCCÈS` | 100 % des actions OK |
| `PARTIEL` | ≥ 1 action ignorée, aucune erreur |
| `ÉCHEC` | ≥ 1 erreur |

### 5. Rapports

| Format | Contenu | Emplacement |
|---|---|---|
| **JSON** | Détail complet sans screenshots (léger et lisible) | `reports/report_*.json` |
| **HTML** | Graphique SVG + tableau + screenshots inline, thème sombre | `reports/report_*.html` |
| **Dashboard web** | Graphiques Chart.js dynamiques depuis la DB SQLite | `http://127.0.0.1:5000/` |
| **CSV** | Tous les runs d'une session (run_number, label, ms, statut…) | Export via GUI ou dashboard |
| **Log officiel** | Historique mensuel des exécutions par app/scénario | `logs/official_YYYYMM.csv` |

---

## Installation

```bash
# Cloner
git clone https://github.com/pronoiaque/winghost-rpa.git
cd winghost-rpa

# Environnement virtuel (recommandé)
python -m venv .venv
.venv\Scripts\activate       # Windows

# Dépendances
pip install -r requirements.txt
```

> **Windows uniquement** : `pywin32` et `psutil` capturent le nom de l'application active ; `screeninfo` clippe les screenshots aux limites de chaque moniteur ; `pystray` gère l'icône de zone de notification du mode automatique. Toutes sont des dépendances standard.

---

## Utilisation

### Interface graphique (recommandé)

```bat
winghost.bat
# ou
python gui.py
```

### Workflow typique

1. Saisissez un **nom de scénario** et, optionnellement, le **nom de l'application cible**
2. Cliquez **RECORD** → effectuez votre scénario → **STOP RECORD**
3. La session apparaît dans la liste des scénarios
4. Réglez le **nombre de répétitions** (1–99) et l'**intervalle** entre les runs (secondes)
5. *(Optionnel)* Cochez **« Vérifier le contexte visuel (OCR) »** pour n'exécuter chaque clic/saisie que si l'écran correspond à l'enregistrement (réglez alors le **seuil OCR**). **Décoché par défaut** → rejeu direct sans vérification
6. Cliquez **REPLAY** → WinGhost exécute, mesure, persiste tout en DB et log officiel
7. Consultez l'onglet **Journal** (officiel en 1er, debug en sous-onglet) ou **Stats long-terme**
8. Renommez ou supprimez un scénario via les boutons ✎ / 🗑 dans la liste

### Mode automatique (surveillance planifiée)

1. Sélectionnez le scénario à surveiller
2. Réglez l'**intervalle en minutes** (par défaut **30**, conformément à la spec métier)
3. Cliquez **⏱ Démarrer l'automatique** → WinGhost rejoue le scénario en boucle
4. La fenêtre se **réduit dans la zone de notification** (systray) ; un clic sur l'icône la restaure
5. À chaque cycle : persistance DB + ligne dans le journal officiel
6. En cas d'**échec**, un **gros popup rouge** s'affiche avec le détail des actions fautives

### Gestion des scénarios

- **Renommer** (✎) : met à jour le fichier JSON et la base SQLite
- **Supprimer** (🗑) : supprime le fichier après confirmation — irréversible

### Ligne de commande

```bash
# Enregistrer (avec nom et application cible)
python recorder.py --name="Connexion O" --app="Outlook"

# Rejouer la dernière session (1 fois) — sans vérification OCR (défaut v6.3)
python replayer.py

# Rejouer une session précise 5 fois avec 30 s d'intervalle
python replayer.py scenarios/scenario_20260612_143200.json --runs=5 --interval=30

# Activer la vérification visuelle OCR (gate strict) — optionnel
python replayer.py scenarios/scenario_20260612_143200.json --visual-gate

# Mode automatique : rejouer en boucle toutes les 30 min (Ctrl+C pour arrêter)
python scheduler.py scenarios/scenario_20260612_143200.json --interval-min=30

# Mode automatique AVEC vérification OCR
python scheduler.py scenarios/scenario_20260612_143200.json --interval-min=30 --visual-gate

# Dashboard web seul (sans GUI)
python report_server.py [--port=8080]
```

---

## Dashboard web

Lancez depuis le GUI (**🌐 Dashboard Web**) ou directement :

```bash
python report_server.py
# → http://127.0.0.1:5000/
```

| URL | Description |
|---|---|
| `/` | Liste des sessions : runs, avg global, dernier run |
| `/session/<id>` | Tendance avg/max par run · heatmap horaire · stats par bouton · historique |
| `/run/<id>` | Détail d'un run : actions, statuts, screenshots, temps de réponse |
| `/api/session/<id>/export.csv` | Téléchargement CSV brut |
| `/api/session/<id>/data` | Données JSON (intégration externe) |
| `/api/run/<id>/data` | Données JSON d'un run |

---

## Structure du projet

```
winghost-rpa/
├── recorder.py          # Enregistreur (pynput + EasyOCR + app_name + label OCR)
├── replayer.py          # Rejoueur : simple, multi-run, screenshots, persistance DB + log officiel
├── stats_db.py          # Couche SQLite : sessions / runs / action_results
├── official_log.py      # Log officiel CSV mensuel (app, scénario, durée, statut)
├── scheduler.py         # Mode automatique (daemon) : rejoue en boucle toutes les N min
├── report_server.py     # Dashboard Flask (Chart.js, export CSV, 2 métriques de temps)
├── gui.py               # Interface CustomTkinter v6.2 (thème clair CHU + logo + splash + systray)
├── chu_logo.py          # Logo coquille CHU (SVG + rendu Pillow), palette CHU
├── requirements.txt     # Dépendances pip
├── pyproject.toml       # Métadonnées du projet
├── winghost.bat         # Lanceur Windows
├── install.bat          # Installateur pip
├── assets/              # Logo CHU (logo_chu.svg / logo_chu.png)
├── scenarios/           # Scénarios JSON enregistrés (v4)
├── sessions/            # Sessions JSON v1/v2 (rétrocompatibilité)
├── reports/             # Rapports JSON + HTML par run
├── logs/                # Logs officiels CSV mensuels (official_YYYYMM.csv)
└── winghost_stats.db    # Base SQLite (créée automatiquement au premier replay)
```

---

## Format de scénario (JSON v3)

```json
{
  "version": "3.0",
  "scenario_name": "Connexion admin",
  "target_app": "Outlook",
  "recorded_at": "20260612_143200",
  "action_count": 12,
  "actions": [
    {
      "index": 1,
      "action_type": "move",
      "timestamp": 1749730319.5,
      "x": 820, "y": 400,
      "delay_before": 0.12
    },
    {
      "index": 2,
      "action_type": "click",
      "timestamp": 1749730320.0,
      "x": 850, "y": 420,
      "button": "left",
      "delay_before": 1.234,
      "app_name": "MonApplication",
      "visual_context": {
        "ocr_text": "Connexion | Identifiant | Mot de passe",
        "label": "Connexion",
        "screenshot_region": [770, 340, 160, 160]
      }
    }
  ]
}
```

> `target_app` (v5) est facultatif : s'il est renseigné, il prime sur le nom d'application détecté automatiquement dans le journal officiel.
> Les sessions v1 (`"1.0"`) et v2 (`"2.0"`) restent entièrement compatibles avec le replayer.
> Les scénarios v6 incluent des actions `"move"` (mouvements souris) sans `visual_context` — rétrocompatibles avec les anciens replayers (action inconnue ignorée).

---

## Schéma SQLite (`winghost_stats.db`)

```
sessions        id · name · scenario_name · filepath · action_count · created_at
runs            id · session_id · run_number · started_at · ended_at
                total · ok_count · skip_count · error_count
                avg_response_ms · max_response_ms
                total_duration_s   ← temps bout-en-bout (horloge réelle)
                app_response_ms    ← temps applicatif cumulé (somme des réponses)
action_results  id · run_id · action_index · action_type · label · app_name · x · y
                ocr_score · visual_ok · response_time_ms · status
                error_msg · screenshot_b64 · replayed_at
```

### Deux métriques de temps

| Métrique | Définition | Où la voir |
|---|---|---|
| **Bout-en-bout** (`total_duration_s`) | Durée d'horloge réelle entre la 1ʳᵉ et la dernière action — inclut pauses et attentes applicatives. C'est la valeur du journal officiel. | Dashboard (carte + colonne), bulle d'info |
| **Applicatif cumulé** (`app_response_ms`) | Somme des temps de réponse mesurés après chaque action — réactivité pure de l'application. | Dashboard (carte + colonne), bulle d'info |

---

## Log officiel (`logs/official_YYYYMM.csv`)

Fichiers mensuels (un par mois), UTF-8 BOM (compatible Excel), séparateur `;`.

```
app_name;scenario_name;execution_date;duration_s;status;ok_count;total_count;run_id
MonApp;Connexion admin;2026-06-12T14:32:00;8.3;SUCCÈS;12;12;42
MonApp;Connexion admin;2026-06-12T15:00:05;9.1;PARTIEL;11;12;43
```

---

## Rapport HTML — aperçu

Chaque rapport HTML standalone inclut :

- **6 cartes** résumé : Total, OK, Ignorées, Erreurs, Avg réponse, Max réponse
- **Graphique SVG** : barres par action (🟦 OK / 🟨 ignoré / 🟥 erreur), ligne de moyenne en tirets
- **Tableau complet** : `#`, `Type`, `Cible`, `App`, `Score OCR`, `Visuel OK`, `Réponse (s)`, `Screenshot`, `Statut`
- **Screenshots** inline : miniatures 48 px, zoom ×3.5 au survol de la souris

---

## Dépendances

| Package | Usage |
|---|---|
| `pyautogui` | Contrôle souris/clavier + screenshots |
| `pynput` | Écoute des événements natifs |
| `easyocr` | OCR français + anglais |
| `Pillow` | Traitement d'images |
| `numpy` | Comparaison pixel-à-pixel |
| `customtkinter` | Interface graphique moderne (v4) |
| `flask` | Dashboard web dynamique |
| `pystray` | Icône de zone de notification du mode automatique (v5) |
| `pywin32` | Capture du nom d'application Windows en premier plan |
| `psutil` | Résolution du nom de processus depuis le PID |
| `screeninfo` | Détection multi-moniteurs (clipping des screenshots) |

---

## Licence

MIT — voir [LICENSE](LICENSE)

## Auteur

Olivier Bendries — [@pronoiaque](https://github.com/pronoiaque)
