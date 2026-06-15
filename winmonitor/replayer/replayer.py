"""
replayer.py — Orchestrateur de la Couche 2 (+ déclenche le chrono Couche 3).

Pour chaque action :

  1. ANCRAGE  — re-localise la cible via `matchTemplate` (retry jusqu'à
     ANCHOR_RETRY_TIMEOUT). Si l'ancrage échoue, repli sur les coordonnées
     enregistrées mises à l'échelle DPI/RDP + capture d'un screenshot de
     diagnostic dans FALLBACK_DIR.
  2. DISPATCH — relève t_action puis injecte l'entrée (chemin rapide).
  3. CHRONO   — mesure le temps de réponse visuel (t_action → écran stable).

Le résultat (`RunResult`) porte une mesure par action, prête à être persistée
par la Couche 3.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from winmonitor import config
from winmonitor.kpi.chrono import ResponseMeasure, measure_response
from winmonitor.recorder.scenario import CLICK_TYPES, Action, Scenario
from winmonitor.replayer.anchor import locate_template
from winmonitor.replayer.dpi import DpiAdapter
from winmonitor.replayer.injector import Injector

_MAX_DELAY = 5.0   # plafond du tempo rejoué entre deux actions (évite les attentes absurdes)


@dataclass
class ActionOutcome:
    index: int
    type: str
    response_ms: float
    stable: bool
    timed_out: bool
    anchored: bool             # True si l'ancrage visuel a réussi
    anchor_confidence: float
    anchor_scale: float
    x: int | None = None
    y: int | None = None
    status: str = "ok"         # "ok" | "fallback" | "timeout"


@dataclass
class RunResult:
    scenario: str
    started_at: str            # ISO 8601 UTC
    time_slot: str
    outcomes: list[ActionOutcome] = field(default_factory=list)

    @property
    def total_response_ms(self) -> float:
        return sum(o.response_ms for o in self.outcomes)

    @property
    def status(self) -> str:
        if any(o.status == "timeout" for o in self.outcomes):
            return "failed"
        if any(o.status == "fallback" for o in self.outcomes):
            return "degraded"
        return "ok"


def _load_png(path: Path) -> np.ndarray | None:
    try:
        import cv2

        img = cv2.imread(str(path))
        if img is not None:
            return img
    except Exception:
        pass
    try:
        from PIL import Image

        return np.asarray(Image.open(path).convert("RGB"))[:, :, ::-1].copy()
    except Exception:
        return None


class Replayer:
    """Rejoue un scénario et collecte les temps de réponse visuels."""

    def __init__(self, grabber=None, injector=None) -> None:
        from winmonitor.recorder.screenshot import ScreenGrabber

        self.grabber = grabber or ScreenGrabber()
        cw, ch = self.grabber.screen_size()
        self.current_size = (cw, ch)
        self.injector = injector or Injector(self.current_size)

    # ─── API publique ──────────────────────────────────────────────────────────
    def run(self, scenario: Scenario, scenario_dir: Path) -> RunResult:
        scenario_dir = Path(scenario_dir)
        dpi = DpiAdapter(tuple(scenario.screen_size), self.current_size)
        result = RunResult(
            scenario=scenario.name,
            started_at=datetime.now(timezone.utc).isoformat(),
            time_slot=config.slot_for(datetime.now()),
        )

        for action in scenario.actions:
            self._respect_tempo(action.delta)
            result.outcomes.append(self._play(action, scenario_dir, dpi))

        return result

    # ─── Détail d'une action ────────────────────────────────────────────────────
    def _play(self, action: Action, scenario_dir: Path, dpi: DpiAdapter) -> ActionOutcome:
        x, y = action.x, action.y
        anchored = False
        confidence = 0.0
        scale = 1.0
        status = "ok"

        if action.type in CLICK_TYPES + ("scroll", "move") and action.anchor:
            x, y, anchored, confidence, scale = self._resolve_anchor(action, scenario_dir, dpi)
            if not anchored:
                status = "fallback"

        # t_action : relevé juste avant de déclencher l'action (référence du chrono).
        t_action = time.perf_counter()
        self._dispatch(action, x, y)
        measure: ResponseMeasure = measure_response(self.grabber, t_action)

        if measure.timed_out:
            status = "timeout"

        return ActionOutcome(
            index=action.index,
            type=action.type,
            response_ms=round(measure.response_ms, 1),
            stable=measure.stable,
            timed_out=measure.timed_out,
            anchored=anchored,
            anchor_confidence=round(confidence, 4),
            anchor_scale=scale,
            x=x,
            y=y,
            status=status,
        )

    def _resolve_anchor(self, action, scenario_dir, dpi):
        """Retry d'ancrage ; repli coords mises à l'échelle + screenshot diagnostic."""
        template = _load_png(scenario_dir / action.anchor.template)
        offset = tuple(action.anchor.click_offset)
        scales = dpi.search_scales()
        deadline = time.perf_counter() + config.ANCHOR_RETRY_TIMEOUT
        best = None

        if template is not None:
            while time.perf_counter() < deadline:
                screen = self.grabber.grab()
                m = locate_template(screen, template, offset, scales=scales)
                if m.found:
                    return m.x, m.y, True, m.confidence, m.scale
                best = m
                time.sleep(config.ANCHOR_RETRY_INTERVAL)

        # Échec d'ancrage → repli coordonnées enregistrées mises à l'échelle DPI.
        fx, fy = dpi.scale_point(action.x or 0, action.y or 0)
        self._save_fallback(action.index)
        conf = best.confidence if best else 0.0
        return fx, fy, False, conf, 1.0

    def _dispatch(self, action: Action, x, y) -> None:
        t = action.type
        if t == "click":
            self.injector.click(x, y, action.button or "left")
        elif t == "double_click":
            self.injector.click(x, y, action.button or "left", double=True)
        elif t == "right_click":
            self.injector.click(x, y, "right")
        elif t == "middle_click":
            self.injector.click(x, y, "middle")
        elif t == "move":
            self.injector.move(x, y)
        elif t == "scroll":
            self.injector.scroll(x, y, action.scroll_dy)
        elif t == "text":
            self.injector.type_text(action.text or "")
        elif t == "key":
            self.injector.press_key(action.key or "")
        # "wait" : rien à injecter, le tempo a déjà été respecté.

    def _save_fallback(self, index: int) -> None:
        try:
            config.FALLBACK_DIR.mkdir(parents=True, exist_ok=True)
            img = self.grabber.grab()
            path = config.FALLBACK_DIR / f"fallback_{index:03d}_{int(time.time())}.png"
            try:
                import cv2

                cv2.imwrite(str(path), img)
            except Exception:
                from PIL import Image

                Image.fromarray(img[:, :, ::-1]).save(path)
        except Exception:
            pass

    @staticmethod
    def _respect_tempo(delta: float) -> None:
        if delta and delta > 0:
            time.sleep(min(delta, _MAX_DELAY))
