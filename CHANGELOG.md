# Changelog

Toutes les modifications notables de WinGhost RPA sont documentées ici.  
Format : [Keep a Changelog](https://keepachangelog.com/fr/1.1.0/) — versionnage [SemVer](https://semver.org/lang/fr/).

---

## [3.0.0] — 2026-06-11

### Ajouté

#### 🔁 Multi-run — Replay N fois la même session
- `MultiReplayRunner` dans `replayer.py` : lance N exécutions consécutives d'une session avec intervalle configurable entre chaque run
- Spinner **Répétitions (1–99)** et champ **Intervalle (s)** dans les options replay du GUI
- Journal temps réel avec en-têtes de run colorés (`═══ Run X/N ═══`)
- Chaque run est persisté individuellement en base SQLite (run_id, started_at, stats agrégées)
- L'arrêt anticipé (bouton STOP) interrompt proprement le run en cours et les runs suivants

#### 💾 Base de données SQLite — Statistiques long-terme
- `stats_db.py` (nouveau) : schéma SQLite avec tables `sessions`, `runs`, `action_results`
- Chaque replay (simple ou multi) insère automatiquement les résultats dans `winghost_stats.db`
- Fonctions d'analyse : `get_label_stats()` (avg/max/min ms + taux de succès par label), `get_hourly_stats()` (avg ms par heure de la journée 0–23), `get_run_trend()` (tendance par run)
- `export_csv()` : export CSV complet de tous les runs d'une session

#### 📸 Screenshots post-action
- Option **Capturer screenshots post-action** dans les options replay (GUI)
- `ActionReplayer(capture_screenshots=True)` : après chaque action exécutée, capture une région élargie (120 px) autour des coordonnées en PNG base64
- `ActionResult.screenshot_b64` : champ optionnel (None si capture désactivée)
- Screenshots affichés en miniatures dans le rapport HTML (survol = zoom ×3.5) et dans le dashboard web
- Le rapport JSON n'inclut pas les screenshots (garde le fichier lisible) ; le HTML les embarque inline

#### 🌐 Dashboard web dynamique — `report_server.py` (nouveau)
- Serveur Flask local lancé par le bouton **🌐 Dashboard Web** du GUI (port 5000 par défaut)
- **Page d'accueil** `/` : liste toutes les sessions avec nombre de runs, avg global, date du dernier run
- **Détail session** `/session/<id>` :
  - Graphique **tendance avg/max (ms) par run** (Chart.js)
  - **Heatmap horaire** : avg réponse + nb d'exécutions par heure de la journée (barres doubles)
  - Tableau des runs avec statut OK/warn/error et liens vers le détail
  - Tableau **Temps de réponse par bouton** (avg/max/min/taux OK par label)
  - Bouton export CSV
- **Détail run** `/run/<id>` : tableau complet avec screenshots inline, badge de statut, erreurs
- **API JSON** : `/api/session/<id>/data`, `/api/run/<id>/data`
- **Export CSV** : `/api/session/<id>/export.csv` (déclenche un téléchargement)
- Thème dark identique à l'interface Tkinter (même palette CSS)
- Le serveur s'arrête proprement à la fermeture de la fenêtre principale

#### 📊 Onglet « Stats long-terme » dans le GUI
- Troisième onglet dans le panneau droit
- Combobox de sélection de session, bouton Actualiser
- Treeview **Historique des runs** : run#, date, total/OK/ignorées/erreurs, avg/max (ms)
- Treeview **Stats par bouton** : label, type, nb exécutions, avg/max/min (ms), taux OK
- Bouton **⬇ Export CSV** : sauvegarde via dialogue fichier (encodage UTF-8 BOM pour Excel)
- Rafraîchissement automatique après chaque replay terminé

#### 🔧 Améliorations `ActionResult`
- `.response_time_ms` (property) : temps en millisecondes (plus lisible que les secondes)
- `.status` (property) : `"ok"` | `"skip"` | `"error"` (utilisé en DB et dans les rapports)
- `.x`, `.y` exposés sur le résultat (coordonnées de l'action, utiles pour la capture screenshot)

### Modifié
- `replayer.py` : `save_report()` crée le JSON **sans** screenshots (lisible) + HTML **avec** screenshots inline
- `replayer.py` : `save_to_db()` méthode publique sur `ActionReplayer` — persistance SQLite en une ligne
- `gui.py` : titre → `WinGhost RPA v3`, layout élargi (980×700), option screenshots dans replay
- `gui.py` : la barre de progression affiche le run courant (`Run X/N`) en multi-run
- `gui.py` : après un multi-run, bascule automatiquement sur l'onglet Stats
- `requirements.txt` : ajout `flask>=3.0.0`

### Compatibilité
- Sessions v1/v2 entièrement compatibles en replay
- `save_report_html()` (alias v2) supprimé — utiliser `save_report()` qui génère les deux fichiers

---

## [2.0.0] — 2026-06-11

### Ajouté

#### 🏷️ Champ `label` — nom humain de la cible OCR
- `VisualContext.label` : nom court déduit de l'OCR brut, stocké dans chaque action de session JSON
- Algorithme `derive_label()` : choisit le fragment OCR le plus court (≥ 2 car.), limité à 4 mots, avec fallback selon le type d'action (`"Valider"`, `"Champ Identifiant"`, `"Saisie"`, etc.)
- `ActionResult.label` : champ exposé dans le replayer et les rapports
- **Tableau Rapport** : nouvelle colonne `Cible` (ACCENT2 / orange) en remplacement du dump OCR brut
- **Journal temps réel** : le label apparaît entre crochets `[Valider]` dans chaque ligne de log
- **Rapport JSON** : champ `"label"` dans chaque action
- **Rapport HTML** : colonne `Cible` lisible, tooltip sur erreur, label dans le graphique

#### 🌐 Export HTML avec graphique des temps de réponse
- `replayer.save_report()` génère désormais **deux fichiers** en une passe : `.json` + `.html`
- `replayer._build_html_report()` : rapport HTML standalone (aucune dépendance externe)
  - 6 cartes résumé (Total, OK, Ignorées, Erreurs, Avg, Max)
  - **Graphique SVG dynamique** : barres colorées par statut (vert=OK, jaune=ignoré, rouge=erreur), ligne de moyenne en tirets orange, valeurs affichées au-dessus, tooltips natifs SVG, axe Y avec graduations en secondes
  - Tableau complet avec colonne `Cible`
  - Thème sombre cohérent avec l'interface Tkinter (palette identique)
- Bouton **🌐 Exporter HTML** dans le pied de l'onglet Rapport
  - Si un rapport HTML existe déjà : propose de l'ouvrir directement ou d'en générer un nouveau
  - Ouvre automatiquement le rapport dans le navigateur par défaut
- `replayer.save_report_html()` : alias retournant uniquement le chemin HTML

#### 🖥️ Support multi-moniteurs
- `get_all_monitors()` dans `recorder.py` : détecte tous les moniteurs via `screeninfo` (si installé) ou repli gracieux sur `pyautogui.size()`
- `monitor_for_point(x, y)` : identifie le moniteur contenant un point donné
- `screenshot_region(x, y, padding)` : capture clampée aux limites du moniteur contenant le curseur (pas de débordement sur l'écran adjacent)
- `_take_full_screenshot()` dans le replayer : capture l'ensemble du bureau fusionné
- `_wait_for_screen_change()` : comparaison robuste si la résolution change entre deux captures (recadrage automatique)
- **GUI** : indicateur `🖥  N écrans WxH + WxH…` dans le header, mis à jour au démarrage
- Fenêtre GUI centrée sur le moniteur **principal** (pas nécessairement `(0, 0)`)
- Vérification OCR multi-écran : utilise `screenshot_region()` si les coordonnées sont disponibles
- `screeninfo` ajouté dans `requirements.txt` (optionnel)

### Modifié
- `recorder.py` : `_capture_visual_context()` passe `action_type` à `derive_label()` pour des fallbacks sémantiques
- `recorder.py` : version de session JSON passée de `"1.0"` à `"2.0"`
- `replayer.py` : `_replay_action()` lit `label` depuis la session (v2) ou le déduit depuis l'OCR (v1 rétrocompatible)
- `replayer.py` : log enrichi avec le label `— cible: "Valider"`
- `gui.py` : titre mis à jour → `WinGhost RPA v2`
- `gui.py` : `_update_progress()` affiche le label dans le journal
- `pyproject.toml` : version `2.0.0`

### Compatibilité
- Les sessions v1 (`"version": "1.0"`) sont entièrement compatibles : le label est déduit à la volée depuis l'`ocr_text` au moment du replay
- `screeninfo` est optionnel : si absent, la capture se replie sur le moniteur principal sans erreur

---

## [1.0.0] — 2026-06-11

### Ajouté
- `recorder.py` — enregistrement des actions utilisateur (clic, double-clic, clic droit, saisie, touches spéciales) avec capture OCR EasyOCR par région
- `replayer.py` — replay avec vérification visuelle OCR (score `difflib`) et mesure du temps de réponse applicatif par polling pixel-à-pixel
- `gui.py` — interface Tkinter sombre : bouton Record/Stop, liste de sessions, curseur seuil OCR, journal coloré temps réel, onglet Rapport avec tableau et export JSON
- Format de session JSON versionné (`"version": "1.0"`) avec `visual_context` par action
- Format de rapport JSON avec résumé (`total`, `ok`, `skipped`, `errors`, `avg_response_time_s`, `max_response_time_s`)
- FAILSAFE PyAutoGUI (coin supérieur gauche)
- Bufferisation des frappes clavier en actions `type` cohérentes
- Détection automatique du double-clic (seuil `DOUBLE_CLICK_GAP = 0.3 s`)
- Support GPU optionnel pour EasyOCR (commenté dans `requirements.txt`)
- `README.md`, `LICENSE` MIT, `CONTRIBUTING.md`

---

## [À venir] — non planifié

- Seuil OCR configurable par action individuelle (stocké dans le JSON de session)
- Mode `--dry-run` : vérification OCR sans exécution des actions
- Chiffrement AES des sessions sensibles
- Backend alternatif Playwright pour les applications web
- Alertes automatiques (email / webhook) si le temps de réponse dépasse un seuil
- Comparaison côte-à-côte de deux sessions (régression de performance)
