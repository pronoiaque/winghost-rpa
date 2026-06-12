"""
scheduler.py — Mode automatique (daemon) pour WinGhost RPA v5.

Rejoue un scénario en boucle à intervalle régulier (par défaut toutes les
30 minutes), persiste chaque cycle en base SQLite et dans le journal officiel,
et notifie l'appelant via des callbacks (utilisé par l'IHM pour le suivi en
systray et l'alerte sur échec).

Conçu pour répondre à la spec métier :
    « Automatiser le script afin qu'il puisse tourner toutes les 30 mins »

API :
    SchedulerRunner(
        ocr_similarity_min=0.40,
        on_cycle_start=callable(cycle:int),
        on_cycle_done=callable(cycle:int, results:list, status:str, run_id:int),
        on_progress=callable(current:int, total:int, result),
        on_wait=callable(cycle:int, next_run_epoch:float),
        stop_event=threading.Event | None,
    )

    .run_forever(session_path, interval_minutes=30.0, max_cycles=0)
        Boucle jusqu'à stop() (ou max_cycles si > 0). Bloquant : à lancer
        dans un thread dédié.

    .stop()
        Demande l'arrêt propre (interrompt l'attente entre deux cycles).

Le champ `status` transmis aux callbacks reprend les constantes de
official_log : "SUCCÈS" | "PARTIEL" | "ÉCHEC".
"""

import logging
import threading
import time
from pathlib import Path
from typing import Callable, Optional

import official_log

log = logging.getLogger("scheduler")


def _status_from_results(results: list) -> str:
    """Déduit le statut officiel d'un cycle à partir des résultats d'actions."""
    if not results:
        return official_log.STATUS_FAILURE
    has_error = any(getattr(r, "status", "") == "error" for r in results)
    has_skip  = any(getattr(r, "status", "") == "skip"  for r in results)
    if has_error:
        return official_log.STATUS_FAILURE
    if has_skip:
        return official_log.STATUS_PARTIAL
    return official_log.STATUS_SUCCESS


class SchedulerRunner:
    def __init__(
        self,
        ocr_similarity_min: float = 0.40,
        on_cycle_start: Optional[Callable[[int], None]] = None,
        on_cycle_done:  Optional[Callable[[int, list, str, int], None]] = None,
        on_progress:    Optional[Callable[[int, int, object], None]] = None,
        on_wait:        Optional[Callable[[int, float], None]] = None,
        stop_event:     Optional[threading.Event] = None,
    ):
        self.ocr_similarity_min = ocr_similarity_min
        self.on_cycle_start     = on_cycle_start
        self.on_cycle_done      = on_cycle_done
        self.on_progress        = on_progress
        self.on_wait            = on_wait
        self._stop_event        = stop_event or threading.Event()
        self._cycle_count       = 0

    @property
    def cycle_count(self) -> int:
        return self._cycle_count

    def stop(self):
        self._stop_event.set()

    def run_forever(
        self,
        session_path: Path,
        interval_minutes: float = 30.0,
        max_cycles: int = 0,
    ) -> None:
        # Import tardif : EasyOCR est lourd à initialiser, on évite de le faire
        # au simple import du module.
        from replayer import ActionReplayer

        self._stop_event.clear()
        self._cycle_count = 0
        interval_s = max(1.0, interval_minutes * 60.0)

        log.info("Mode automatique démarré : %s toutes les %.1f min.",
                 session_path.name, interval_minutes)

        # Un seul ActionReplayer réutilisé entre les cycles (EasyOCR chargé une fois)
        replayer = ActionReplayer(
            ocr_similarity_min=self.ocr_similarity_min,
            on_progress=self.on_progress,
        )

        while not self._stop_event.is_set():
            self._cycle_count += 1
            cycle = self._cycle_count

            if self.on_cycle_start:
                self.on_cycle_start(cycle)
            log.info("═══ Cycle automatique #%d ═══", cycle)

            results: list = []
            run_id = 0
            try:
                replayer._stop_event = self._stop_event
                session = replayer.load_session(session_path)
                results = replayer.replay(session)
                run_id  = replayer.save_to_db(session_path)
            except Exception as e:
                log.error("Cycle #%d en erreur : %s", cycle, e)

            status = _status_from_results(results)
            if self.on_cycle_done:
                self.on_cycle_done(cycle, results, status, run_id)
            log.info("Cycle #%d terminé — statut %s.", cycle, status)

            if max_cycles and cycle >= max_cycles:
                log.info("max_cycles (%d) atteint — arrêt.", max_cycles)
                break

            # Attente interruptible jusqu'au prochain cycle
            next_run = time.time() + interval_s
            if self.on_wait:
                self.on_wait(cycle, next_run)
            log.info("Prochain cycle dans %.1f min…", interval_minutes)
            self._stop_event.wait(timeout=interval_s)

        log.info("Mode automatique arrêté après %d cycle(s).", self._cycle_count)


# ─── CLI ──────────────────────────────────────────────────────────────────────

def main():
    import sys

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [SCHEDULER] %(levelname)s — %(message)s",
    )

    session_path = None
    interval_min = 30.0
    max_cycles   = 0
    args = sys.argv[1:]

    if args and not args[0].startswith("--"):
        session_path = Path(args.pop(0))
    for a in args:
        if a.startswith("--interval-min="):
            interval_min = float(a.split("=", 1)[1])
        elif a.startswith("--max-cycles="):
            max_cycles = int(a.split("=", 1)[1])

    if session_path is None:
        from replayer import SCENARIOS_DIR, SESSIONS_DIR
        candidates = sorted(SCENARIOS_DIR.glob("scenario_*.json")) if SCENARIOS_DIR.exists() else []
        if not candidates:
            candidates = sorted(SESSIONS_DIR.glob("session_*.json")) if SESSIONS_DIR.exists() else []
        if not candidates:
            print("Aucun scénario trouvé.")
            sys.exit(1)
        session_path = candidates[-1]

    print(f"Mode automatique : {session_path.name} toutes les {interval_min} min "
          f"(Ctrl+C pour arrêter)")
    runner = SchedulerRunner(
        on_cycle_done=lambda c, r, s, rid: print(f"  Cycle #{c} → {s} (run_id={rid})"),
    )
    try:
        runner.run_forever(session_path, interval_minutes=interval_min, max_cycles=max_cycles)
    except KeyboardInterrupt:
        runner.stop()
        print("\nArrêt demandé.")


if __name__ == "__main__":
    main()
