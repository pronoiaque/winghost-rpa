# Changelog

Toutes les modifications notables de WinGhost RPA sont documentées ici.  
Format : [Keep a Changelog](https://keepachangelog.com/fr/1.1.0/) — versionnage [SemVer](https://semver.org/lang/fr/).

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

- Seuil OCR configurable par action (stocké dans le JSON de session)
- Mode `--dry-run` : vérification OCR sans exécution des actions
- Chiffrement AES des sessions sensibles
- Backend alternatif Playwright pour les applications web
- Export CSV du rapport
