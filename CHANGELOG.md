# Changelog

Toutes les modifications notables de WinGhost RPA sont documentées ici.  
Format : [Keep a Changelog](https://keepachangelog.com/fr/1.1.0/) — versionnage [SemVer](https://semver.org/lang/fr/).

---

## [6.3.0] — 2026-06-13

### Ajouté

#### 📦 Binaire Windows x64 unique (PyInstaller)
- **`winghost.spec`** : recette PyInstaller produisant un exécutable **one-file** `dist/WinGhost.exe` (application fenêtrée, icône CHU générée depuis le PNG)
- **Build léger** : EasyOCR / PyTorch sont **exclus** du binaire (≈ 200 Mo au lieu de ~1,5–2,5 Go). L'ancrage visuel OCR étant optionnel et décoché par défaut, le RPA pur (clics, saisies, molette, glisser, mouvements, timing, dashboard, mode automatique) fonctionne tel quel
- **`.github/workflows/build-windows.yml`** : compilation automatique sur `windows-latest` (PyInstaller ne cross-compile pas) — artefact à chaque exécution, **Release** avec l'exe attaché sur tag `v*`
- **`requirements-build.txt`** : dépendances du build léger (sans easyocr/torch)
- **`paths.py`** : résolution des chemins compatible binaire gelé — ressources en lecture seule via `sys._MEIPASS`, données inscriptibles (scénarios, rapports, journaux, base SQLite) à côté de l'exe ou dans `%APPDATA%\WinGhost`
- **EasyOCR rendu optionnel** : `recorder.py` / `replayer.py` l'importent paresseusement ; absent, l'enregistrement se fait sans label OCR (screenshots conservés) et le gate visuel se désactive proprement (avertissement clair dans l'IHM)
- Tous les dossiers d'exécution (`sessions/`, `scenarios/`, `reports/`, `logs/`, `winghost_stats.db`) passent par `paths.data_dir()` ; l'enregistrement 32 bits (`i386`/win32) n'est pas supporté (PyTorch n'a plus de wheels 32 bits — x64 uniquement)

### Modifié

#### 🔓 La vérification visuelle OCR devient optionnelle (désactivée par défaut)
- Auparavant : « les clics et saisies n'étaient rejoués que si le contexte visuel correspondait » (gate OCR **toujours actif**)
- Désormais : ce comportement est une **option décochée par défaut** — case **« Vérifier le contexte visuel (OCR) »** dans *Options replay*
- **Par défaut, toutes les actions sont rejouées sans vérification OCR** → rejeu plus rapide et plus robuste (plus de faux négatifs qui faisaient sauter des clics)
- Le **seuil OCR** (slider) n'est désormais pertinent que lorsque la case est cochée ; il est **grisé** quand l'option est désactivée
- Quand l'option est décochée, **EasyOCR n'est pas sollicité** pendant le replay (les colonnes *Score OCR* / *Visuel* affichent « — »)

### Détails techniques
- `ActionReplayer(..., visual_gate: bool = False)` : nouveau paramètre. Le bloc de vérification OCR de `_replay_action` n'est exécuté que si `visual_gate` est vrai
- `MultiReplayRunner(..., visual_gate=False, reader=None)` et `SchedulerRunner(..., visual_gate=False, reader=None)` propagent l'option (replay multiple et mode automatique)
- EasyOCR n'est initialisé (ou le lecteur partagé utilisé) que si `visual_gate=True`
- IHM : `self._visual_gate_var` (BooleanVar, défaut `False`) transmis aux trois constructeurs ; `_on_visual_gate_toggle()` active/grise le slider de seuil

---

## [6.2.0] — 2026-06-12

### Ajouté

#### 🎨 Habillage aux couleurs officielles du CHU de Toulouse
- **Thème clair institutionnel** : interface en thème clair aux couleurs officielles du CHU de Toulouse
- Palette officielle extraite du SVG CHU : dégradé `#adce80` → `#4eaf98` → `#3c9aac` → `#006471` → `#004d6b`
- Texte principal et bandeau : **bleu marine officiel `#004d6b`** ; fonds `#FFFFFF` / `#EAF3F6` (bleu-vert très clair)
- Boutons, onglets et accents recolorés en bleu-vert `#3c9aac` et vert clair `#adce80`

#### 🐚 Logo « coquille » CHU (`chu_logo.py` + `assets/logo_chu.svg`)
- Nouveau module `chu_logo` : génère le logo **coquille CHU de Toulouse** avec le dégradé radial officiel (SVG scalable + rendu Pillow)
- Silhouette officielle reproduite fidèlement depuis le SVG CHU (chemin `M34.1514,6.2165…`)
- Dégradé radial avec rotation `-42.284°` : vert clair → teal → bleu-vert → bleu foncé → marine
- Deux petits éléments graphiques à la base de la coquille (`#004d6b`) inclus
- Texte `CHU / DE / TOULOUSE` en bleu marine officiel intégré dans le SVG
- Logo affiché dans le **bandeau d'en-tête**, le **splash screen**, l'**icône de fenêtre** et l'**icône systray**
- `assets/logo_chu.svg` (vectoriel) + `assets/logo_chu.png` (raster) livrés

---

## [6.1.0] — 2026-06-12

### Corrigé

#### 🖱️ Tous les inputs souris désormais capturés et rejoués
- **Bug v6** : seuls les *mouvements* étaient des nouveautés visibles ; en condition réelle, les **clics ne se rejouaient pas** alors que les mouvements (non soumis à l'OCR) défilaient — symptôme « la souris bouge mais ne clique pas »
- **Cause** : le contexte OCR d'un clic tombait sous le seuil par défaut (`0.40`) → l'action était *ignorée* (skip strict), tandis que les `move` passaient toujours
- **Correctif** : seuil OCR par défaut abaissé à **`0.25`** (`OCR_SIMILARITY_MIN`, slider GUI) pour réduire les faux négatifs, **tout en conservant le gate OCR strict** demandé par la spec (« rejeu uniquement si match »)

### Ajouté

#### 🆕 Inputs souris complets (recorder + replayer)
- **Clic milieu** (`middle_click`) : auparavant enregistré à tort comme clic gauche ; désormais distingué et rejoué via `pyautogui.middleClick`
- **Molette** (`scroll`) : nouvel handler `on_scroll` → action `scroll` (`scroll_dx`/`scroll_dy`), rejouée via `pyautogui.scroll` / `hscroll` (facteur `SCROLL_REPLAY_AMOUNT = 100`)
- **Glisser-déposer** (`drag`) : détection press→déplacement→release (seuil `DRAG_MIN_DIST_PX = 12`) ; les mouvements intermédiaires (bouton maintenu) ne sont plus enregistrés comme `move` isolés ; rejeu via `pyautogui.moveTo` + `dragTo`
- Le glisser et le clic milieu restent soumis au **gate OCR** (contexte visuel capturé au press), conformément à la spec

### Détails techniques
- `Action` enrichi : champs `x2`, `y2` (destination du drag), `scroll_dx`, `scroll_dy`
- `recorder` : suivi de l'état bouton (`_press_info`, `_button_down`) ; les `move` sont ignorés tant qu'un bouton est maintenu
- Le double-clic reste détecté correctement (non confondu avec un drag)

---

## [6.0.0] — 2026-06-12

### Ajouté

#### 🖱️ Enregistrement des mouvements souris (`recorder.py`)
- Nouvelle action `"move"` : les déplacements du curseur sont consignés dans le scénario JSON
- Throttling : 10 FPS max (`MOVE_THROTTLE_S = 0.10`) et distance minimum 15 px (`MOVE_MIN_DIST_PX = 15`)
- Aucun `visual_context` sur les `move` — pas d'OCR, pas de screenshot, taille des scénarios maîtrisée
- Rejeu via `pyautogui.moveTo(x, y, duration=…)` pour une trajectoire fidèle et naturelle

#### ⏳ Splash screen de démarrage (`gui.py`)
- Écran d'accueil (480×260 px) affiché dès le lancement, **avant** la fenêtre principale
- Barre de progression animée pendant le chargement d'EasyOCR avec message de statut en temps réel
- La fenêtre principale n'est affichée qu'à la fin (`deiconify` après fermeture du splash)

#### ♻️ Lecteur OCR partagé (`reader=`)
- EasyOCR initialisé **une seule fois** (splash), puis transmis via `reader=` à `ActionRecorder` et `ActionReplayer`
- Si `reader=None`, chaque classe charge son propre reader (comportement historique préservé)

#### 🎯 Rejeu OCR strict
- Les `move` s'exécutent directement sans vérification OCR ni mesure de réponse
- Clics / saisies / touches : conditionnés par le seuil OCR — **uniquement si match**

### Corrigé

#### 🐛 `CTkSegmentedButton.bind()` → `NotImplementedError`
- Remplacé par `configure(command=lambda _tab: …)`, supporté dans toutes les versions de CustomTkinter

---

## [5.0.0] — 2026-06-12

### Ajouté

#### 🔁 Mode automatique (daemon) — `scheduler.py` (nouveau)
- `SchedulerRunner` : rejoue un scénario **en boucle à intervalle régulier** (par défaut **30 min**, conformément à la spec métier « tourner toutes les 30 mins »)
- Réutilise un seul `ActionReplayer` entre les cycles (EasyOCR chargé une fois)
- Persistance DB + écriture du journal officiel à **chaque cycle**
- Attente inter-cycles interruptible (arrêt propre via `stop()`)
- Callbacks : `on_cycle_start`, `on_cycle_done(cycle, results, status, run_id)`, `on_progress`, `on_wait`
- CLI : `python scheduler.py <scenario.json> --interval-min=30 [--max-cycles=N]`

#### 📥 Réduction en zone de notification (systray)
- Au démarrage du mode automatique, la fenêtre se **réduit dans le systray** (via `pystray`)
- Icône dédiée + menu : **Ouvrir WinGhost** (clic par défaut), **Arrêter l'automatique**, **Quitter**
- Un clic sur l'icône restaure la fenêtre (`deiconify` + `lift` + `focus`)
- Repli gracieux sur une réduction classique (`iconify`) si `pystray` est indisponible

#### 🚨 Alerte sur échec — gros popup
- `_show_failure_popup()` : `CTkToplevel` plein cadre, rouge, avec ✘ géant, nom du scénario, n° de cycle et **liste des actions fautives**
- Déclenché dès qu'une exécution se solde par un statut `ÉCHEC` — en mode automatique **comme** en replay manuel (simple et multi-run)
- Restaure automatiquement la fenêtre depuis le systray + signal sonore (`bell`)

#### 🎯 Application cible (`target_app`)
- Champ **App** dans la section Enregistrement : l'utilisateur saisit le nom de l'application visée
- Stocké au niveau du scénario (`"target_app"` dans le JSON), pré-rempli à la sélection d'un scénario
- **Prioritaire** sur le nom de processus détecté automatiquement pour la colonne `app_name` du journal officiel
- CLI recorder : `python recorder.py --name="…" --app="…"`

#### ⏱️ Deux métriques de temps distinctes
- `app_response_ms` (nouvelle colonne `runs`) : **temps applicatif cumulé** = somme des temps de réponse (réactivité pure)
- `total_duration_s` (existant) : **temps de bout en bout** = durée d'horloge réelle (valeur du journal officiel)
- Dashboard : **deux cartes** + **deux colonnes** dans l'historique des runs, chacune avec une **bulle d'aide** (`info` au survol) expliquant la différence
- Les deux métriques sont ajoutées à l'export CSV (`export_csv`)

### Modifié
- `stats_db.py` : colonne `app_response_ms` sur `runs` + migration `_migrate` ; `finish_run()` accepte `app_response_ms` ; `export_csv()` inclut `total_duration_s` et `app_response_ms`
- `replayer.py` : `save_to_db()` calcule et persiste `app_response_ms` ; `write_official_log()` privilégie `target_app` du scénario
- `recorder.py` : `ActionRecorder(scenario_name, target_app)` ; champ `target_app` sauvegardé dans le scénario
- `report_server.py` : page session enrichie (cartes + colonnes + tooltips CSS `.tip`)
- `gui.py` : titre → `v5` ; champ Application cible ; bloc « Mode automatique » (intervalle min + bouton) ; intégration systray ; popup d'échec ; arrêt propre du scheduler à la fermeture
- `requirements.txt` / `pyproject.toml` : ajout `pystray>=0.19.4`, version `5.0.0`

### Corrigé
- `report_server.py` : f-string à guillemets imbriqués (ligne de la colonne OCR) qui cassait la compatibilité Python 3.10/3.11 (PEP 701 réservé à 3.12+) — extraction des valeurs avant le f-string

### Compatibilité
- Scénarios v1/v2/v3 toujours pleinement compatibles
- Bases SQLite antérieures migrées automatiquement (ajout de `app_response_ms`)
- `pystray` optionnel à l'exécution : sans lui, le mode automatique tourne quand même (fenêtre réduite classiquement)

---

## [4.0.0] — 2026-06-12

### Ajouté

#### 🎨 Interface CustomTkinter — refonte complète de `gui.py`
- Migration Tkinter → **CustomTkinter** : thème dark arrondi, widgets CTk natifs (`CTkFrame`, `CTkButton`, `CTkEntry`, `CTkLabel`, `CTkSlider`, `CTkTabview`, `CTkScrollableFrame`, `CTkInputDialog`)
- `CTkToolTip` : bulles d'aide sur tous les boutons et contrôles (délai 600 ms, disparition au clic/mouvement)
- `_Spinbox` : composant spinbox personnalisé (boutons −/+, validation entier 1–99)
- `_ScenarioRow` : ligne de liste de scénario avec icône 🎬, badge compteur de runs, bouton renommer ✎ et bouton supprimer 🗑
- Champ **Nom du scénario** en haut du panneau gauche — prérempli automatiquement pour chaque enregistrement

#### 🗂️ Gestion des scénarios
- **Renommer** un scénario (✎) : dialogue `CTkInputDialog`, mise à jour du JSON et de la DB SQLite
- **Supprimer** un scénario (🗑) : confirmation, suppression du fichier JSON
- Fichiers sauvegardés dans `scenarios/` (format `scenario_YYYYMMDD_HHMMSS.json`) — `sessions/` conservé pour rétrocompatibilité v1/v2

#### 📋 Log officiel CSV (`official_log.py`, nouveau)
- `LOGS_DIR = Path("logs")` — fichiers mensuels `logs/official_YYYYMM.csv`
- Séparateur `;`, encodage UTF-8 BOM (compatible Excel)
- Colonnes : `app_name`, `scenario_name`, `execution_date`, `duration_s`, `status`, `ok_count`, `total_count`, `run_id`
- Statuts : `SUCCÈS` (100 % OK), `PARTIEL` (≥ 1 skip, 0 erreur), `ÉCHEC` (≥ 1 erreur)
- `init_logs()`, `append_entry(...)`, `get_recent_entries(max_lines=200)`, `get_all_log_paths()`
- Écrit automatiquement à la fin de chaque `save_to_db()` dans `replayer.py`

#### 🪵 Log dual (Journal officiel + Log debug)
- L'onglet **Journal** contient désormais un `CTkTabview` interne :
  - **Journal officiel** : tableau des exécutions chargé depuis `official_log.get_recent_entries()`, rafraîchi après chaque replay
  - **Log debug** : journal technique temps réel (actions, scores OCR, erreurs, screenshots), accessible à la demande

#### 📸 Screenshots systématiques (160 px)
- Option `capture_screenshots` supprimée — capture toujours active, région 160 px (était 120 px)
- `ActionReplayer` et `MultiReplayRunner` : paramètre `capture_screenshots` retiré de l'API
- `SCREENSHOT_REGION_PAD = 160` dans `replayer.py`

#### 🖥️ Nom d'application capturé (`app_name`)
- `get_foreground_app() -> str` dans `recorder.py` : nom du processus Windows en premier plan via `win32gui` + `win32process` + `psutil` ; repli gracieux sur `""` si absents
- Champ `app_name` ajouté dans `Action` (recorder), `ActionResult` (replayer), `action_results` (DB), `export_csv()` (DB)
- Affiché dans le log officiel (application la plus fréquente du run, via `Counter`)

#### 📊 Stats long-terme — corrections profondes
- `_refresh_stats_silent()` : actualisation sans réinitialiser la combobox
- `_refresh_stats_for_index()` : requêtes DB avec `try/except` par treeview, logs d'erreur explicites
- Auto-actualisation à chaque changement d'onglet (`_on_tab_changed`) et après chaque replay terminé
- `_load_stats_sessions()` appelé au démarrage (délai 800 ms)

### Modifié
- `recorder.py` : `SCENARIOS_DIR = Path("scenarios")` — sauvegarde dans `scenarios/`, version JSON `"3.0"`, champ `scenario_name`, champ `app_name` par action, `SCREENSHOT_PADDING = 160`, screenshots toujours capturés
- `replayer.py` : `write_official_log()` méthode publique — calcule durée, statut, app dominante ; appelée par `save_to_db()` ; `_last_session` stocké après `load_session()` ; `SCENARIOS_DIR` en priorité dans la recherche CLI
- `stats_db.py` : colonnes `scenario_name` (sessions), `total_duration_s` (runs), `app_name` (action_results) ; fonction `_migrate(conn)` pour bases existantes ; tous les accesseurs mis à jour
- `gui.py` : titre → `WinGhost RPA v4`, layout 1020×750, `_log_debug()` / `_log_official()` pour les deux canaux
- `requirements.txt` : ajout `customtkinter>=5.2.0`, `pywin32>=306`, `psutil>=5.9.0` (dépendances standard, plus optionnelles) ; `screeninfo` reclassé en dépendance standard
- `pyproject.toml` : version `4.0.0` ; `dependencies` complétées avec `screeninfo`, `flask`, `customtkinter`, `pywin32`, `psutil`

### Supprimé
- Checkbox **Capturer screenshots post-action** dans le GUI (screenshots toujours actifs)
- Paramètre `capture_screenshots` dans `ActionReplayer` et `MultiReplayRunner`

### Compatibilité
- Sessions v1 (`"1.0"`), v2 (`"2.0"`) et v3 (`"3.0"`) entièrement compatibles en replay
- Base SQLite existante migrée automatiquement au premier démarrage (`_migrate`)
- `sessions/` toujours lu pour rétrocompatibilité (`_list_scenario_files`)

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
