# Changelog

Toutes les modifications notables de WinGhost RPA sont documentées ici.  
Format : [Keep a Changelog](https://keepachangelog.com/fr/1.1.0/) — versionnage [SemVer](https://semver.org/lang/fr/).

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
- `README.md` complet pour GitHub
- `LICENSE` MIT
- `.gitignore` Python / Windows / EasyOCR
- `CONTRIBUTING.md`
- `sessions/.gitkeep` et `reports/.gitkeep` pour conserver les dossiers dans Git

---

## [À venir] — non planifié

### Idées en cours d'évaluation
- Export rapport HTML avec graphique SVG des temps de réponse
- Seuil OCR configurable par action (stocké dans le JSON de session)
- Support multi-moniteurs
- Mode `--dry-run` : vérification OCR sans exécution
- Chiffrement AES des sessions sensibles
- Backend alternatif Playwright pour les applications web
