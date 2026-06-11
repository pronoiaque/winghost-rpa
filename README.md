# WinGhost RPA v3

> Enregistreur / Rejoueur RPA Windows avec ancrage visuel OCR, statistiques long-terme multi-run, screenshots post-action, dashboard web dynamique et export CSV.

![License MIT](https://img.shields.io/badge/license-MIT-blue)
![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue)
![Windows](https://img.shields.io/badge/os-Windows-lightgrey)
![Version](https://img.shields.io/badge/version-3.0.0-green)

---

## Nouveautés v3

| Fonctionnalité | Description |
|---|---|
| 🔁 **Multi-run** | Rejoue N fois la même session avec intervalle configurable — accumule les stats sur le long terme |
| 💾 **Base SQLite** | Tous les résultats sont persistés automatiquement dans `winghost_stats.db` |
| 📸 **Screenshots post-action** | Capture PNG de chaque clic/saisie, embarquée dans le rapport HTML (zoom ×3.5 au survol) |
| 🌐 **Dashboard web** | Serveur Flask local avec graphiques Chart.js : tendance par run, heatmap horaire, stats par bouton |
| 📊 **Onglet Stats long-terme** | Historique complet des runs et temps de réponse par bouton directement dans le GUI |
| ⬇ **Export CSV** | Export complet de tous les runs d'une session, compatible Excel (UTF-8 BOM) |

---

## Fonctionnement

### 1. Enregistrement (`recorder.py`)

L'outil écoute les événements souris et clavier via **pynput**. À chaque clic ou saisie :

1. Capture d'écran de la région autour du curseur (±80 px, multi-moniteurs)
2. Reconnaissance OCR (EasyOCR, fr + en) sur cette zone
3. Déduction d'un **label humain** (`"Connexion"`, `"Champ mot de passe"`) depuis le texte OCR
4. Sauvegarde dans `sessions/session_YYYYMMDD_HHMMSS.json`

### 2. Replay simple (`ActionReplayer`)

Pour chaque action enregistrée :

1. **Vérification OCR** : compare le contexte visuel actuel à celui enregistré (score `difflib`)
2. Si le score est inférieur au seuil → action ignorée (l'interface a changé)
3. **Exécution** via PyAutoGUI
4. **Screenshot post-action** (optionnel) : PNG base64 de la région autour du clic
5. **Mesure du temps de réponse** : polling pixel-à-pixel jusqu'au prochain changement d'écran

### 3. Multi-run (`MultiReplayRunner`)

Lance N fois la même session consécutivement, avec pause configurable entre les runs. Chaque run est sauvegardé individuellement en base SQLite. Cela permet d'analyser :

- La **tendance** du temps de réponse au fil des runs
- Les **pics de lag** par heure de la journée (heatmap horaire)
- Le **taux de succès** par bouton sur la durée

### 4. Rapports

| Format | Contenu | Emplacement |
|---|---|---|
| **JSON** | Détail complet sans screenshots (fichier léger et lisible) | `reports/report_*.json` |
| **HTML** | Graphique SVG + tableau + screenshots inline, thème sombre | `reports/report_*.html` |
| **Dashboard web** | Graphiques Chart.js dynamiques depuis la DB SQLite | `http://127.0.0.1:5000/` |
| **CSV** | Tous les runs d'une session (run_number, label, ms, statut…) | Export via GUI ou dashboard |

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

> **`screeninfo`** (multi-moniteurs) est optionnel — repli gracieux sur le moniteur principal si absent.

---

## Utilisation

### Interface graphique (recommandé)

```bat
winghost.bat
# ou
python gui.py
```

### Workflow typique

1. **RECORD** → effectuez votre scénario dans l'application cible → **STOP RECORD**
2. Sélectionnez la session dans la liste à gauche
3. Réglez le **nombre de répétitions** (1–99) et l'**intervalle** entre les runs (secondes)
4. Cochez **Screenshots post-action** pour capturer l'état de l'écran après chaque action
5. Cliquez **REPLAY** → WinGhost exécute et mesure chaque run, persiste tout en DB
6. Consultez l'onglet **Stats long-terme** ou ouvrez le **🌐 Dashboard Web**

### Ligne de commande

```bash
# Enregistrer
python recorder.py [--screenshots]

# Rejouer la dernière session (1 fois)
python replayer.py

# Rejouer une session précise 5 fois avec 30 s d'intervalle
python replayer.py sessions/session_20260611_143200.json --runs=5 --interval=30

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
├── recorder.py          # Enregistreur (pynput + EasyOCR + label OCR)
├── replayer.py          # Rejoueur : simple, multi-run, screenshots, persistance DB
├── stats_db.py          # Couche SQLite : sessions / runs / action_results
├── report_server.py     # Dashboard Flask (Chart.js, export CSV)
├── gui.py               # Interface Tkinter v3
├── requirements.txt     # Dépendances pip
├── pyproject.toml       # Métadonnées du projet
├── winghost.bat         # Lanceur Windows
├── install.bat          # Installateur pip
├── sessions/            # Sessions JSON enregistrées
├── reports/             # Rapports JSON + HTML par run
└── winghost_stats.db    # Base SQLite (créée automatiquement au premier replay)
```

---

## Format de session (JSON v2)

```json
{
  "version": "2.0",
  "recorded_at": "20260611_143200",
  "action_count": 12,
  "actions": [
    {
      "index": 1,
      "action_type": "click",
      "timestamp": 1749644000.0,
      "x": 850, "y": 420,
      "button": "left",
      "delay_before": 1.234,
      "visual_context": {
        "ocr_text": "Connexion | Identifiant | Mot de passe",
        "label": "Connexion",
        "screenshot_region": [770, 340, 160, 160]
      }
    }
  ]
}
```

> Les sessions v1 (`"version": "1.0"`) et v2 sont entièrement compatibles avec le replayer v3.

---

## Schéma SQLite (`winghost_stats.db`)

```
sessions        id · name · filepath · action_count · created_at
runs            id · session_id · run_number · started_at · ended_at
                total · ok_count · skip_count · error_count
                avg_response_ms · max_response_ms
action_results  id · run_id · action_index · action_type · label · x · y
                ocr_score · visual_ok · response_time_ms · status
                error_msg · screenshot_b64 · replayed_at
```

---

## Rapport HTML — aperçu

Chaque rapport HTML standalone inclut :

- **6 cartes** résumé : Total, OK, Ignorées, Erreurs, Avg réponse, Max réponse
- **Graphique SVG** : barres par action (🟦 OK / 🟨 ignoré / 🟥 erreur), ligne de moyenne en tirets
- **Tableau complet** : `#`, `Type`, `Cible`, `Score OCR`, `Visuel OK`, `Réponse (s)`, `Screenshot`, `Statut`
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
| `flask` | Dashboard web dynamique |
| `screeninfo` | Détection multi-moniteurs *(optionnel)* |

---

## Licence

MIT — voir [LICENSE](LICENSE)

## Auteur

Olivier Bendries — [@pronoiaque](https://github.com/pronoiaque)
