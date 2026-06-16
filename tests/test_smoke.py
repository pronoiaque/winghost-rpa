"""
test_smoke.py — Test de fumée des couches « sans IHM » (store, baseline,
dashboard, rapport). N'exige ni écran, ni OpenCV, ni pynput : il valide la
chaîne de données KPI de bout en bout sur un WINMONITOR_HOME temporaire.
"""

import os
import tempfile
from pathlib import Path

# Isole les données AVANT d'importer les modules qui lisent config.HOME.
_TMP = tempfile.mkdtemp(prefix="winmon_test_")
os.environ["WINMONITOR_HOME"] = _TMP


def _fake_run(scenario, slot, total_ms, status="ok"):
    from winmonitor.replayer.replayer import ActionOutcome, RunResult

    r = RunResult(scenario=scenario, started_at="2026-06-15T08:30:00+00:00",
                  time_slot=slot)
    r.outcomes.append(
        ActionOutcome(index=0, type="click", response_ms=total_ms, stable=True,
                      timed_out=False, anchored=True, anchor_confidence=0.95,
                      anchor_scale=1.0, x=10, y=20, status=status)
    )
    return r


def test_store_baseline_dashboard_report():
    from winmonitor.kpi.baseline import compute_baseline
    from winmonitor.kpi.dashboard import build_dashboard
    from winmonitor.kpi.store import MetricsStore
    from winmonitor.scheduler.report import build_daily_report

    store = MetricsStore()
    for ms in (120, 140, 160, 900):     # 900 = pic de latence
        store.insert_run(_fake_run("calc", "08h-09h", ms))

    assert "calc" in store.scenarios()
    assert len(store.runs_for("calc")) == 4

    bl = compute_baseline(store, "calc", "08h-09h")
    assert bl.n == 4
    assert bl.median_ms > 0
    assert bl.p95_ms >= bl.median_ms

    dash = build_dashboard(store)
    assert Path(dash).exists()
    assert "calc" in Path(dash).read_text(encoding="utf-8")

    rep = build_daily_report("2026-06-15", store)
    assert Path(rep).exists()


def test_slot_for():
    from datetime import datetime

    from winmonitor.config import slot_for

    assert slot_for(datetime(2026, 6, 15, 8, 30)) == "08h-09h"
    assert slot_for(datetime(2026, 6, 15, 3, 0)) == "hors-plage"


def test_chrono_diff_pure_numpy():
    import numpy as np

    from winmonitor.kpi.chrono import _mean_abs_diff

    a = np.zeros((10, 10), dtype=np.uint8)
    b = a.copy()
    assert _mean_abs_diff(a, b) == 0.0
    b[:] = 255
    assert _mean_abs_diff(a, b) == 255.0
