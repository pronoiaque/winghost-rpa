"""
baseline.py — Calcul de la baseline et détection de régression.

La baseline d'un scénario, par plage horaire, est résumée par sa médiane et son
p95 historiques. Une mesure courante est « dégradée » si elle dépasse
`p95 * REGRESSION_FACTOR` — signal d'un ralentissement applicatif anormal.
"""

from __future__ import annotations

from dataclasses import dataclass

from winmonitor import config


@dataclass
class Baseline:
    scenario: str
    time_slot: str
    n: int
    median_ms: float
    p95_ms: float

    @property
    def regression_threshold_ms(self) -> float:
        return self.p95_ms * config.REGRESSION_FACTOR


def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    if len(s) == 1:
        return s[0]
    k = (len(s) - 1) * pct
    lo = int(k)
    hi = min(lo + 1, len(s) - 1)
    frac = k - lo
    return s[lo] + (s[hi] - s[lo]) * frac


def median(values: list[float]) -> float:
    return _percentile(values, 0.5)


def compute_baseline(store, scenario: str, time_slot: str | None = None) -> Baseline:
    values = store.response_times(scenario, time_slot)
    return Baseline(
        scenario=scenario,
        time_slot=time_slot or "global",
        n=len(values),
        median_ms=round(median(values), 1),
        p95_ms=round(_percentile(values, 0.95), 1),
    )


def is_regression(value_ms: float, baseline: Baseline) -> bool:
    if baseline.n < 3:
        return False  # pas assez d'historique pour juger
    return value_ms > baseline.regression_threshold_ms
