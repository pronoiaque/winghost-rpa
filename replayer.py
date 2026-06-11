"""
replayer.py — Rejoue une session enregistrée avec vérification visuelle OCR.

Fonctions clés :
  • Vérifie que le contexte OCR autour de chaque cible correspond à ce qui
    a été enregistré (score de similarité configurable).
  • Mesure le temps de réponse applicatif entre l'action automatisée et
    le prochain changement détectable à l'écran.
  • Produit un rapport JSON de timing à la fin du replay.
"""

import json
import time
import datetime
import logging
import difflib
import threading
from pathlib import Path
from typing import Optional, Callable

import pyautogui
import easyocr
import numpy as np
from PIL import Image

# ─── Configuration ────────────────────────────────────────────────────────────

SESSIONS_DIR   = Path("sessions")
REPORTS_DIR    = Path("reports")
REPORTS_DIR.mkdir(exist_ok=True)

OCR_LANGUAGES         = ["fr", "en"]
OCR_SIMILARITY_MIN    = 0.40    # score minimum pour valider la zone (0–1)
RESPONSE_WAIT_MAX     = 10.0    # secondes max pour détecter un changement écran
RESPONSE_POLL_INTERVAL= 0.05   # intervalle de polling pour la détection (s)
SCREEN_DIFF_THRESHOLD = 0.005   # fraction minimale de pixels modifiés (0–1)
SCREENSHOT_PADDING    = 80      # même valeur que dans recorder.py
ACTION_DELAY_MIN      = 0.05    # délai minimum entre actions (s)
PYAUTOGUI_PAUSE       = 0.1     # pause PyAutoGUI entre commandes (s)

pyautogui.PAUSE        = PYAUTOGUI_PAUSE
pyautogui.FAILSAFE     = True   # coin haut-gauche stoppe le script

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [REPLAYER] %(levelname)s — %(message)s"
)
log = logging.getLogger("replayer")

# ─── Résultat par action ──────────────────────────────────────────────────────

class ActionResult:
    def __init__(self, index: int, action_type: str, timestamp: float):
        self.index         = index
        self.action_type   = action_type
        self.timestamp     = timestamp
        self.ocr_match     = None   # float | None
        self.visual_ok     = None   # bool
        self.skipped       = False
        self.error         = None   # str | None
        self.t_action_sent = None   # epoch après exécution de l'action
        self.t_screen_changed = None  # epoch détection changement écran
        self.response_time = None   # float (s)

    def to_dict(self) -> dict:
        return {
            "index":           self.index,
            "action_type":     self.action_type,
            "timestamp":       self.timestamp,
            "ocr_match_score": round(self.ocr_match, 3) if self.ocr_match is not None else None,
            "visual_ok":       self.visual_ok,
            "skipped":         self.skipped,
            "error":           self.error,
            "t_action_sent":   self.t_action_sent,
            "t_screen_changed":self.t_screen_changed,
            "response_time_s": round(self.response_time, 3) if self.response_time is not None else None,
        }

# ─── Replayer principal ───────────────────────────────────────────────────────

class ActionReplayer:
    def __init__(
        self,
        ocr_similarity_min: float = OCR_SIMILARITY_MIN,
        on_progress: Optional[Callable[[int, int, ActionResult], None]] = None,
    ):
        self.ocr_similarity_min = ocr_similarity_min
        self.on_progress = on_progress          # callback UI éventuel
        self._results: list[ActionResult] = []
        self._stop_event = threading.Event()

        log.info("Initialisation EasyOCR…")
        self._reader = easyocr.Reader(OCR_LANGUAGES, gpu=False, verbose=False)
        log.info("EasyOCR prêt.")

    # ── API publique ──────────────────────────────────────────────────────────

    def load_session(self, path: Path) -> dict:
        with open(path, encoding="utf-8") as f:
            return json.load(f)

    def replay(self, session: dict) -> list[ActionResult]:
        """Rejoue toutes les actions de la session. Retourne la liste des résultats."""
        self._results = []
        self._stop_event.clear()
        actions = session.get("actions", [])
        total   = len(actions)

        log.info("Début du replay : %d action(s)", total)

        for i, raw in enumerate(actions):
            if self._stop_event.is_set():
                log.info("Replay interrompu à l'action %d.", i)
                break

            result = self._replay_action(raw, i, total)
            self._results.append(result)

            if self.on_progress:
                self.on_progress(i + 1, total, result)

        log.info("Replay terminé. %d action(s) traitée(s).", len(self._results))
        return self._results

    def stop(self):
        """Arrêt anticipé (appelable depuis un thread UI)."""
        self._stop_event.set()

    def save_report(self, session_path: Path) -> Path:
        ts   = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        stem = session_path.stem
        path = REPORTS_DIR / f"report_{stem}_{ts}.json"

        total     = len(self._results)
        ok_count  = sum(1 for r in self._results if not r.skipped and not r.error)
        skip_count= sum(1 for r in self._results if r.skipped)
        err_count = sum(1 for r in self._results if r.error)

        resp_times = [r.response_time for r in self._results if r.response_time is not None]
        avg_resp   = round(sum(resp_times) / len(resp_times), 3) if resp_times else None
        max_resp   = round(max(resp_times), 3) if resp_times else None

        report = {
            "session_file":  str(session_path),
            "replayed_at":   ts,
            "summary": {
                "total":     total,
                "ok":        ok_count,
                "skipped":   skip_count,
                "errors":    err_count,
                "avg_response_time_s": avg_resp,
                "max_response_time_s": max_resp,
            },
            "actions": [r.to_dict() for r in self._results],
        }

        with open(path, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)

        log.info("Rapport sauvegardé → %s", path)
        return path

    # ── Exécution d'une action ─────────────────────────────────────────────────

    def _replay_action(self, raw: dict, i: int, total: int) -> ActionResult:
        result = ActionResult(
            index       = raw.get("index", i + 1),
            action_type = raw.get("action_type", "unknown"),
            timestamp   = raw.get("timestamp", 0),
        )

        # ── Délai inter-actions ──────────────────────────────────────────────
        delay = max(raw.get("delay_before", 0), ACTION_DELAY_MIN)
        time.sleep(delay)

        # ── Vérification visuelle ────────────────────────────────────────────
        visual_ctx = raw.get("visual_context")
        if visual_ctx and visual_ctx.get("ocr_text"):
            ok, score = self._verify_visual(
                raw.get("x"), raw.get("y"),
                visual_ctx["screenshot_region"],
                visual_ctx["ocr_text"],
            )
            result.ocr_match = score
            result.visual_ok = ok
            if not ok:
                result.skipped = True
                result.error   = (
                    f"Contexte visuel non reconnu "
                    f"(score={score:.2f} < seuil={self.ocr_similarity_min:.2f}) — "
                    f"attendu: {visual_ctx['ocr_text'][:80]!r}"
                )
                log.warning("[%d/%d] Action %d IGNORÉE : %s",
                            i+1, total, result.index, result.error)
                return result
        else:
            result.visual_ok = None  # pas de contexte enregistré

        # ── Capture pré-action (référence pour mesure de réponse) ────────────
        pre_screenshot = self._take_screenshot()

        # ── Exécution ────────────────────────────────────────────────────────
        try:
            self._execute(raw)
            result.t_action_sent = time.time()
        except Exception as e:
            result.error = f"Erreur exécution : {e}"
            log.error("[%d/%d] Action %d ERREUR : %s",
                      i+1, total, result.index, e)
            return result

        log.info("[%d/%d] Action %d (%s) exécutée.",
                 i+1, total, result.index, result.action_type)

        # ── Mesure du temps de réponse applicatif ────────────────────────────
        changed_at = self._wait_for_screen_change(pre_screenshot)
        result.t_screen_changed = changed_at
        if changed_at is not None:
            result.response_time = round(changed_at - result.t_action_sent, 3)
            log.info("    ↳ Temps de réponse : %.3f s", result.response_time)
        else:
            log.info("    ↳ Aucun changement écran détecté dans %.1f s",
                     RESPONSE_WAIT_MAX)

        return result

    # ── Vérification OCR ──────────────────────────────────────────────────────

    def _verify_visual(
        self,
        x: Optional[int], y: Optional[int],
        region: list,
        expected_text: str,
    ) -> tuple[bool, float]:
        """
        Compare le texte OCR actuel de la région avec le texte enregistré.
        Retourne (is_valid, similarity_score).
        """
        try:
            rx, ry, rw, rh = region
            screenshot = pyautogui.screenshot(region=(rx, ry, rw, rh))
            img_np     = np.array(screenshot)
            results    = self._reader.readtext(img_np, detail=0)
            current_text = " | ".join(results).strip()

            score = difflib.SequenceMatcher(
                None,
                expected_text.lower(),
                current_text.lower(),
            ).ratio()

            log.debug("OCR attendu : %r", expected_text[:60])
            log.debug("OCR actuel  : %r — score=%.2f", current_text[:60], score)

            return score >= self.ocr_similarity_min, score

        except Exception as e:
            log.warning("Erreur vérification visuelle : %s", e)
            return False, 0.0

    # ── Exécution de l'action ─────────────────────────────────────────────────

    def _execute(self, raw: dict):
        atype = raw.get("action_type")
        x, y  = raw.get("x"), raw.get("y")

        if atype == "click":
            pyautogui.click(x, y)

        elif atype == "double_click":
            pyautogui.doubleClick(x, y)

        elif atype == "right_click":
            pyautogui.rightClick(x, y)

        elif atype == "type":
            if x and y:
                pyautogui.click(x, y)
                time.sleep(0.1)
            text = raw.get("text", "")
            pyautogui.typewrite(text, interval=0.03)

        elif atype == "key":
            key = raw.get("key", "")
            # Mapping pynput → pyautogui
            key_map = {
                "enter":   "enter",
                "tab":     "tab",
                "escape":  "esc",
                "space":   "space",
                "backspace": "backspace",
                "delete":  "delete",
                "up":      "up",
                "down":    "down",
                "left":    "left",
                "right":   "right",
                "home":    "home",
                "end":     "end",
                "page_up": "pageup",
                "page_down": "pagedown",
                "f1": "f1", "f2": "f2", "f3": "f3", "f4": "f4",
                "f5": "f5", "f6": "f6", "f7": "f7", "f8": "f8",
            }
            pyautogui.press(key_map.get(key, key))

        else:
            raise ValueError(f"Type d'action inconnu : {atype!r}")

    # ── Détection de changement d'écran ───────────────────────────────────────

    def _take_screenshot(self) -> np.ndarray:
        return np.array(pyautogui.screenshot())

    def _wait_for_screen_change(
        self,
        reference: np.ndarray,
    ) -> Optional[float]:
        """
        Attend jusqu'à RESPONSE_WAIT_MAX secondes qu'un changement significatif
        apparaisse à l'écran (différence de pixels > SCREEN_DIFF_THRESHOLD).
        Retourne l'epoch du changement, ou None si timeout.
        """
        deadline = time.time() + RESPONSE_WAIT_MAX
        ref_gray = np.mean(reference, axis=2).astype(np.float32)

        while time.time() < deadline:
            if self._stop_event.is_set():
                return None
            time.sleep(RESPONSE_POLL_INTERVAL)

            current      = self._take_screenshot()
            current_gray = np.mean(current, axis=2).astype(np.float32)
            diff         = np.abs(current_gray - ref_gray)
            changed_frac = np.mean(diff > 10)   # pixels ayant changé > 10 niveaux

            if changed_frac >= SCREEN_DIFF_THRESHOLD:
                return time.time()

        return None


# ─── CLI simple ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        sessions = sorted(SESSIONS_DIR.glob("session_*.json"))
        if not sessions:
            print("Aucune session trouvée dans", SESSIONS_DIR)
            sys.exit(1)
        session_path = sessions[-1]
        print(f"Dernière session : {session_path}")
    else:
        session_path = Path(sys.argv[1])

    replayer = ActionReplayer()
    session  = replayer.load_session(session_path)
    results  = replayer.replay(session)
    report   = replayer.save_report(session_path)

    print(f"\nRapport → {report}")
    print(f"Actions : {len(results)} | "
          f"OK : {sum(1 for r in results if not r.skipped and not r.error)} | "
          f"Ignorées : {sum(1 for r in results if r.skipped)} | "
          f"Erreurs : {sum(1 for r in results if r.error)}")
