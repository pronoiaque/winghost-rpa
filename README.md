# 👻 WinGhost RPA

> **Record. Verify. Replay. Report.**  
> Automatisation de bureau Windows avec ancrage visuel OCR — sans framework lourd, sans dépendance cloud.

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue?logo=python&logoColor=white)](https://www.python.org/)
[![Platform](https://img.shields.io/badge/Platform-Windows-0078d4?logo=windows&logoColor=white)](https://www.microsoft.com/windows)
[![License](https://img.shields.io/badge/License-MIT-green)](LICENSE)
[![EasyOCR](https://img.shields.io/badge/OCR-EasyOCR-orange)](https://github.com/JaidedAI/EasyOCR)
[![PyAutoGUI](https://img.shields.io/badge/Automation-PyAutoGUI-yellow)](https://pyautogui.readthedocs.io/)

---

## Pourquoi WinGhost ?

La plupart des outils RPA open-source rejouent les actions **sans vérifier ce qu'il y a vraiment à l'écran**. Un décalage de fenêtre, une pop-up inattendue, un délai réseau — et le script clique dans le vide.

WinGhost résout ça en trois temps :

1. **Enregistrement** : chaque action utilisateur (clic, saisie, touche) est capturée avec son **contexte visuel OCR** — le texte détecté autour du point d'action devient une ancre.
2. **Vérification** : au moment du replay, le contexte OCR actuel est comparé à celui enregistré. Sous le seuil de similarité → l'action est ignorée, pas exécutée à l'aveugle.
3. **Mesure** : entre l'action automatisée et le premier changement visible à l'écran, WinGhost chronomètre la **réponse de l'application cible** et produit un rapport de timing détaillé.

---

## Démonstration rapide

```
python gui.py
```

```
┌─────────────────────────────────────────────────────────┐
│  WinGhost RPA                               Prêt        │
├──────────────┬──────────────────────────────────────────┤
│  ⬤ RECORD    │  ████████████████████░░░░  14 / 18       │
│              │                                          │
│  Sessions    │  Journal                    Rapport      │
│  ──────────  │  [14:32:01] ✔ click         ⏱ 0.312 s   │
│  session_... │  [14:32:02] ✔ type          ⏱ 0.087 s   │
│  session_... │  [14:32:03] ⚠ IGNORÉ OCR=0.21           │
│              │  [14:32:04] ✔ key:enter     ⏱ 1.847 s   │
│  ▶ REPLAY    │                                          │
│  ■ STOP      │  Total 18 | OK 16 | Ignorées 1 | Err 1  │
└──────────────┴──────────────────────────────────────────┘
```

---

## Fonctionnalités

| Fonctionnalité | Détail |
|---|---|
| **Enregistrement clavier + souris** | Clics simples, double-clics, clics droits, saisies texte (bufferisées), touches spéciales |
| **Ancrage visuel OCR** | EasyOCR (fr + en) sur une région ±80 px autour de chaque action |
| **Vérification avant replay** | Score `difflib.SequenceMatcher` — seuil réglable de 0 à 1 |
| **Mesure de réponse applicative** | Polling pixel-par-pixel (50 ms) — temps entre action et changement écran |
| **Rapport JSON structuré** | Par action : OCR score, statut, response_time, erreur éventuelle |
| **Interface Tkinter sombre** | Sans dépendance CDN, compatible réseau hospitalier isolé |
| **FAILSAFE PyAutoGUI** | Coin haut-gauche stoppe immédiatement le replay |
| **Thread-safe** | Record et replay dans des threads séparés, UI non bloquée |

---

## Structure du projet

```
winghost-rpa/
│
├── recorder.py          # Script 1 — Enregistreur d'actions
├── replayer.py          # Script 2 — Rejeu + mesure de temps de réponse
├── gui.py               # Script 3 — Interface graphique Tkinter
│
├── sessions/            # Sessions JSON générées automatiquement
│   └── session_YYYYMMDD_HHMMSS.json
│
├── reports/             # Rapports de replay
│   └── report_session_*_YYYYMMDD_HHMMSS.json
│
├── requirements.txt
└── README.md
```

---

## Installation

### Prérequis

- Python **3.10** ou supérieur
- Windows 10 / 11 (PyAutoGUI + pynput natifs Windows)
- ~300 Mo d'espace disque (modèles EasyOCR téléchargés au premier lancement)

### Étapes

```bash
# 1. Cloner le dépôt
git clone https://github.com/pronoiaque/winghost-rpa.git
cd winghost-rpa

# 2. (Recommandé) Environnement virtuel
python -m venv .venv
.venv\Scripts\activate

# 3. Dépendances
pip install -r requirements.txt
```

> **Premier lancement** : EasyOCR télécharge automatiquement ses modèles de langue (~100 Mo, une seule fois, mis en cache dans `~/.EasyOCR/`).

### Accélération GPU (optionnel)

Si vous disposez d'une carte NVIDIA avec CUDA :

```bash
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu118
```

Puis dans `recorder.py` et `replayer.py`, remplacer `gpu=False` par `gpu=True`.

---

## Utilisation

### Interface graphique

```bash
python gui.py
```

#### Workflow complet

**1 — Enregistrer une session**

- Cocher « Capturer les screenshots » si vous voulez inclure les captures PNG dans le JSON (base64, utile pour le débogage).
- Cliquer **⬤ RECORD**.
- Effectuer vos actions dans l'application cible (navigateur, ERP, client lourd…).
- Cliquer **■ STOP RECORD**.
- La session apparaît dans la liste avec son horodatage.

**2 — Rejouer**

- Sélectionner la session dans la liste (ou cliquer **Parcourir…** pour un fichier externe).
- Ajuster le **seuil OCR** dans le curseur Options (voir [Réglage du seuil](#réglage-du-seuil-ocr) ci-dessous).
- Cliquer **▶ REPLAY**.
- Le journal affiche chaque action en temps réel, colorée selon son statut.

**3 — Rapport**

- L'onglet **Rapport** s'ouvre automatiquement en fin de session.
- Chaque ligne indique : index, type, score OCR, validation visuelle, temps de réponse, statut.
- Cliquer **Exporter JSON** pour sauvegarder le rapport où vous le souhaitez.

**Arrêt d'urgence** : bouton **■ STOP** dans l'interface, ou déplacer la souris dans le **coin supérieur gauche** de l'écran (FAILSAFE PyAutoGUI).

---

### Ligne de commande

#### Enregistrement

```bash
python recorder.py                  # standard
python recorder.py --screenshots    # inclut les captures PNG (base64) dans le JSON
```

Appuyer sur `Entrée` pour arrêter. La session est sauvegardée dans `sessions/`.

#### Replay

```bash
python replayer.py                              # rejoue la dernière session
python replayer.py sessions/session_xyz.json    # session spécifique
```

Le rapport est écrit dans `reports/`.

---

## Format JSON de session

```json
{
  "version": "1.0",
  "recorded_at": "20260611_143000",
  "action_count": 5,
  "actions": [
    {
      "index": 1,
      "action_type": "click",
      "timestamp": 1751234567.0,
      "x": 420,
      "y": 310,
      "button": "left",
      "text": null,
      "key": null,
      "visual_context": {
        "ocr_text": "Identifiant | Mot de passe | Se connecter",
        "screenshot_region": [340, 230, 160, 160],
        "screenshot_b64": null
      },
      "delay_before": 1.24
    },
    {
      "index": 2,
      "action_type": "type",
      "timestamp": 1751234569.2,
      "x": 420,
      "y": 310,
      "text": "olivier.bendries",
      "visual_context": {
        "ocr_text": "Identifiant | Saisir votre identifiant",
        "screenshot_region": [340, 230, 160, 160]
      },
      "delay_before": 2.18
    }
  ]
}
```

### Types d'action enregistrés

| `action_type` | Déclencheur | Contexte OCR capturé |
|---|---|---|
| `click` | Clic gauche | Oui |
| `double_click` | 2 clics gauches ≤ 0,3 s | Oui (remplace le dernier `click`) |
| `right_click` | Clic droit | Oui |
| `type` | Rafale de frappe | Oui (position curseur à la fin) |
| `key` | Touche spéciale | Oui pour Enter, Tab, Escape |

---

## Format JSON de rapport

```json
{
  "session_file": "sessions/session_20260611_143000.json",
  "replayed_at": "20260611_143512",
  "summary": {
    "total": 18,
    "ok": 16,
    "skipped": 1,
    "errors": 1,
    "avg_response_time_s": 0.312,
    "max_response_time_s": 1.847
  },
  "actions": [
    {
      "index": 1,
      "action_type": "click",
      "ocr_match_score": 0.87,
      "visual_ok": true,
      "skipped": false,
      "error": null,
      "t_action_sent": 1751237712.4,
      "t_screen_changed": 1751237712.7,
      "response_time_s": 0.312
    },
    {
      "index": 3,
      "action_type": "click",
      "ocr_match_score": 0.21,
      "visual_ok": false,
      "skipped": true,
      "error": "Contexte visuel non reconnu (score=0.21 < seuil=0.40) — attendu: 'Valider | Annuler'",
      "response_time_s": null
    }
  ]
}
```

---

## Réglage du seuil OCR

Le seuil `OCR_SIMILARITY_MIN` (défaut : **0,40**) contrôle la tolérance de la vérification visuelle.

| Valeur | Comportement | Cas d'usage |
|---|---|---|
| `0.20 – 0.35` | Permissif — accepte des interfaces très dynamiques | Applications avec données changeantes, horodatages à l'écran |
| `0.40 – 0.55` | Équilibré — recommandé pour la plupart des cas | **Valeur par défaut** |
| `0.60 – 0.80` | Strict — exige une correspondance visuelle forte | Formulaires statiques, interfaces figées |
| `> 0.80` | Très strict — risque de nombreux faux-positifs | Rarement utile |

> **Conseil** : démarrez à 0,40, rejouez une première fois, consultez les scores OCR dans le rapport, puis affinez.

---

## Mesure du temps de réponse applicatif

Chaque action du replay fait l'objet d'une mesure en trois étapes :

```
  t₀                t₁                        t₂
   │                 │                          │
   │  screenshot     │  action exécutée         │  changement écran détecté
   │  de référence   │  (clic / saisie / key)   │  (≥ 0,5 % pixels modifiés)
   └─────────────────┴──────────────────────────┘
                                ◄── response_time ──►
```

- **Polling** : toutes les 50 ms (configurable via `RESPONSE_POLL_INTERVAL`).
- **Seuil de détection** : 0,5 % des pixels ayant varié de plus de 10 niveaux de gris (configurable via `SCREEN_DIFF_THRESHOLD`).
- **Timeout** : 10 secondes sans changement → `response_time_s: null` dans le rapport.

> Pour des applications très réactives (réponse < 50 ms), abaisser `RESPONSE_POLL_INTERVAL` à `0.02`. Pour des applications lentes (chargement > 10 s), augmenter `RESPONSE_WAIT_MAX`.

---

## Constantes configurables

Toutes les constantes sont en haut de chaque script Python, sans fichier de config externe.

### `recorder.py`

| Constante | Défaut | Description |
|---|---|---|
| `SCREENSHOT_PADDING` | `80` px | Demi-taille de la région OCR autour du clic |
| `OCR_LANGUAGES` | `["fr", "en"]` | Langues EasyOCR (voir [liste complète](https://www.jaided.ai/easyocr/)) |
| `DOUBLE_CLICK_GAP` | `0.3` s | Intervalle maximum pour détecter un double-clic |
| `SESSIONS_DIR` | `sessions/` | Répertoire de sortie des sessions |

### `replayer.py`

| Constante | Défaut | Description |
|---|---|---|
| `OCR_SIMILARITY_MIN` | `0.40` | Seuil de validation visuelle (0–1) |
| `RESPONSE_WAIT_MAX` | `10.0` s | Timeout pour la détection de réponse écran |
| `RESPONSE_POLL_INTERVAL` | `0.05` s | Fréquence de polling pour la détection |
| `SCREEN_DIFF_THRESHOLD` | `0.005` | Fraction minimale de pixels modifiés (0,5 %) |
| `ACTION_DELAY_MIN` | `0.05` s | Délai minimum forcé entre deux actions |
| `PYAUTOGUI_PAUSE` | `0.1` s | Pause PyAutoGUI entre commandes |
| `SCREENSHOT_PADDING` | `80` px | Même valeur que dans recorder.py |
| `REPORTS_DIR` | `reports/` | Répertoire de sortie des rapports |

---

## Dépendances

```
pyautogui>=0.9.54    # Automatisation souris / clavier / screenshot
pynput>=1.7.6        # Écoute d'événements clavier et souris
easyocr>=1.7.1       # OCR multi-langues embarqué
Pillow>=10.0.0       # Traitement d'images
numpy>=1.24.0        # Calcul matriciel pour la comparaison de screenshots
```

Tkinter est inclus avec Python standard — aucune installation supplémentaire.

---

## Limites connues

- **Windows uniquement** dans sa version actuelle. Linux/macOS nécessiteraient des ajustements sur pynput et les coordonnées écran.
- **Écrans multi-moniteurs** : PyAutoGUI capture le moniteur principal par défaut. Les coordonnées sont absolues ; un second écran à gauche peut décaler les régions OCR.
- **Haute résolution / DPI** : sur les écrans 4K avec mise à l'échelle Windows > 100 %, les coordonnées PyAutoGUI peuvent diverger de la position réelle. Tester avec `pyautogui.FAILSAFE = True` pour stopper en cas de dérive.
- **Applications DirectX / OpenGL** : PyAutoGUI ne peut pas interagir avec des zones de rendu 3D exclusif (jeux plein écran, etc.).
- **Première exécution lente** : EasyOCR télécharge ~100 Mo de modèles au premier lancement. Les exécutions suivantes utilisent le cache local.

---

## Contribuer

Les contributions sont les bienvenues. Pour proposer une modification :

```bash
# 1. Forker le dépôt sur GitHub

# 2. Créer une branche descriptive
git checkout -b feature/ma-fonctionnalite

# 3. Committer avec un message clair
git commit -m "feat: description courte de la modification"

# 4. Pousser et ouvrir une Pull Request
git push origin feature/ma-fonctionnalite
```

### Idées d'évolution

- [ ] Export du rapport en HTML avec graphique des temps de réponse
- [ ] Seuil OCR configurable **par action** (stocké dans le JSON de session)
- [ ] Support multi-moniteurs
- [ ] Mode "dry run" : vérifie les contextes OCR sans exécuter les actions
- [ ] Playwright / Selenium en backend alternatif pour les applications web
- [ ] Chiffrement AES des sessions contenant des données sensibles (mots de passe)

---

## Licence

[MIT](LICENSE) — Olivier Bendries / pronoiaque

---

## Remerciements

- [EasyOCR](https://github.com/JaidedAI/EasyOCR) — OCR open-source multi-langues (JaidedAI)
- [PyAutoGUI](https://github.com/asweigart/pyautogui) — Al Sweigart
- [pynput](https://github.com/moses-palmer/pynput) — Moses Palmér
