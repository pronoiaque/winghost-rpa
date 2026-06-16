"""
chrono.py — Chronomètre VISUEL : t_action → écran stable.

C'est la pièce maîtresse de la refonte. Plutôt que de chronométrer l'injection
des frappes (latence parasite, cause des « hésitations » de la v6.x), on mesure
le temps que met l'ÉCRAN à se stabiliser après une action :

  1. juste après avoir déclenché l'action (t_action), on capture l'écran en
     boucle à intervalle court ;
  2. tant que deux captures successives diffèrent (diff. moyenne de pixels
     > seuil), l'appli est réputée « en train de répondre » ;
  3. dès que l'écran reste identique pendant N images consécutives, il est
     « stable » → le temps de réponse = (dernier changement − t_action).

Ce temps reflète la VRAIE réactivité de l'application CHU (RDP, Win32, web),
indépendamment de la vitesse du clavier/souris.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

import numpy as np

from winmonitor import config


@dataclass
class ResponseMeasure:
    response_ms: float       # durée entre t_action et la stabilisation de l'écran
    stable: bool             # True si l'écran s'est stabilisé avant le timeout
    timed_out: bool          # True si STABLE_TIMEOUT atteint sans stabilité
    frames: int              # nombre de captures effectuées (diagnostic)


def _mean_abs_diff(a: np.ndarray, b: np.ndarray) -> float:
    """Différence moyenne (niveaux de gris) entre deux captures de même taille."""
    if a.shape != b.shape:
        return 255.0  # tailles différentes → changement maximal
    a16 = a.astype(np.int16)
    b16 = b.astype(np.int16)
    return float(np.abs(a16 - b16).mean())


def measure_response(
    grabber,
    t_action: float,
    region: tuple[int, int, int, int] | None = None,
    *,
    diff_threshold: float = config.STABLE_DIFF_THRESHOLD,
    stable_frames: int = config.STABLE_FRAMES,
    poll_interval: float = config.STABLE_POLL_INTERVAL,
    timeout: float = config.STABLE_TIMEOUT,
) -> ResponseMeasure:
    """
    Mesure le temps de réponse visuel à partir de `t_action`
    (= valeur `time.perf_counter()` relevée juste avant de déclencher l'action).
    """
    prev = _grab_gray(grabber, region)
    frames = 1
    stable_count = 0
    last_change = t_action
    deadline = t_action + timeout

    while time.perf_counter() < deadline:
        time.sleep(poll_interval)
        cur = _grab_gray(grabber, region)
        frames += 1
        if _mean_abs_diff(prev, cur) <= diff_threshold:
            stable_count += 1
            if stable_count >= stable_frames:
                return ResponseMeasure(
                    response_ms=max(0.0, (last_change - t_action) * 1000.0),
                    stable=True,
                    timed_out=False,
                    frames=frames,
                )
        else:
            stable_count = 0
            last_change = time.perf_counter()
        prev = cur

    return ResponseMeasure(
        response_ms=(time.perf_counter() - t_action) * 1000.0,
        stable=False,
        timed_out=True,
        frames=frames,
    )


def _grab_gray(grabber, region):
    img = grabber.grab(region)
    if img.ndim == 3:
        # Conversion légère BGR → gris sans dépendre d'OpenCV ici.
        return (img[:, :, 0] * 0.114 + img[:, :, 1] * 0.587 + img[:, :, 2] * 0.299).astype(
            np.uint8
        )
    return img
