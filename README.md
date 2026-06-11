# WinGhost RPA v2

> Enregistreur / Rejoueur RPA Windows avec ancrage visuel OCR, mesure de temps de réponse, export HTML et support multi-moniteurs.

![License MIT](https://img.shields.io/badge/license-MIT-blue)
![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue)
![Windows](https://img.shields.io/badge/os-Windows-lightgrey)
![Version](https://img.shields.io/badge/version-2.0.0-green)

---

## Nouveautés v2

| Fonctionnalité | Description |
|---|---|
| 🏷️ **Champ `label`** | Nom humain de la cible déduit de l'OCR (`"Valider"`, `"Champ Login"`) — affiché dans le journal, le tableau et le rapport |
| 🌐 **Export HTML** | Rapport standalone avec graphique SVG des temps de réponse, colonne `Cible` lisible, thème sombre |
| 🖥️ **Multi-moniteurs** | Capture correctement clampée au moniteur contenant le curseur — fonctionne avec 2, 3 moniteurs ou plus |

---

## Fonctionnement

### 1. Enregistrement (`recorder.py`)
L'outil écoute les événements souris et clavier via **pynput**. À chaque clic ou saisie :
1. Il prend une **capture d'écran** de la région autour du curseur (±80 px, multi-moniteurs)
2. Il fait une **reconnaissance OCR** (EasyOCR, fr + en) sur cette zone
3. Il déduit un **label humain** (ex : `"Connexion"`, `"Champ mot de passe"`) depuis le texte OCR
4. Il sauvegarde l'action dans `sessions/session_YYYYMMDD_HHMMSS.json`

### 2. Replay (`replayer.py`)
Pour chaque action enregistrée :
1. **Vérification visuelle** : compare le contexte OCR actuel à celui enregistré (score `difflib`)
2. Si le score est inférieur au seuil → action ignorée (interface a changé)
3. **Exécution** de l'action via PyAutoGUI
4. **Mesure du temps de réponse** : polling pixel-à-pixel jusqu'au prochain changement d'écran

### 3. Rapport
- **JSON** : `reports/report_*.json` — détail complet avec `label`, scores OCR, temps de réponse
- **HTML** : `reports/report_*.html` — rapport visuel standalone avec graphique SVG interactif

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

> **`screeninfo`** (multi-moniteurs) est optionnel — si absent, la capture se replie sur le moniteur principal.

---

## Utilisation

### Interface graphique (recommandé)
```bat
winghost.bat
# ou
python gui.py
```

### Ligne de commande
```bash
# Enregistrer
python recorder.py [--screenshots]

# Rejouer la dernière session
python replayer.py

# Rejouer une session précise
python replayer.py sessions/session_20260611_143200.json
```

---

## Structure du projet

```
winghost-rpa/
├── recorder.py          # Enregistreur (pynput + EasyOCR + label)
├── replayer.py          # Rejoueur + export JSON/HTML
├── gui.py               # Interface Tkinter v2 (multi-moniteurs, export HTML)
├── requirements.txt     # Dépendances pip
├── pyproject.toml       # Métadonnées du projet
├── winghost.bat         # Lanceur Windows
├── install.bat          # Installateur pip
├── sessions/            # Sessions JSON enregistrées
└── reports/             # Rapports JSON + HTML
```

---

## Format de session v2 (JSON)

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

> Les sessions v1 (`"version": "1.0"`) sont entièrement compatibles avec le replayer v2.

---

## Rapport HTML — aperçu

Le rapport HTML généré inclut :
- **6 cartes** résumé : Total, OK, Ignorées, Erreurs, Avg réponse, Max réponse
- **Graphique SVG** : barres colorées (🟦 OK / 🟨 ignoré / 🟥 erreur), ligne de moyenne en tirets
- **Tableau complet** avec colonnes : `#`, `Type`, `Cible`, `Score OCR`, `Visuel OK`, `Réponse (s)`, `Statut`

---

## Dépendances

| Package | Usage |
|---|---|
| `pyautogui` | Contrôle souris/clavier + screenshots |
| `pynput` | Écoute des événements natifs |
| `easyocr` | OCR français + anglais |
| `Pillow` | Traitement d'images |
| `numpy` | Comparaison pixel-à-pixel |
| `screeninfo` | Détection multi-moniteurs *(optionnel)* |

---

## Licence

MIT — voir [LICENSE](LICENSE)

## Auteur

Olivier Bendries — [@pronoiaque](https://github.com/pronoiaque)
