"""
chu_logo.py — Logo « coquille » inspiré de l'identité visuelle du CHU de Toulouse
(coquille Saint-Jacques, dégradé bleu → vert).

⚠️  Reconstruction libre destinée à l'habillage interne de l'outil. Ce n'est PAS
    le fichier officiel déposé : pour un usage officiel, remplacez
    assets/logo_chu.svg par le SVG fourni par la direction de la communication.

Le module expose :
  • COLORS                : la palette CHU (hex)
  • build_svg()           : retourne le code SVG de la coquille (scalable)
  • write_svg(path)       : écrit le SVG sur disque
  • render_logo(size)     : retourne une image Pillow RGBA de la coquille
                            (utilisée dans l'en-tête de la GUI, sans dépendance SVG)

Géométrie : un éventail de N segments ouvert vers le haut, bord supérieur
festonné (petits arcs), nervures rayonnant depuis la charnière basse.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Optional

# ─── Palette CHU Toulouse (reconstruction) ────────────────────────────────────

COLORS = {
    "blue":        "#0091CE",   # bleu institutionnel
    "blue_dark":   "#006FA3",
    "teal":        "#00A99D",   # transition du dégradé
    "green":       "#8BC53F",   # vert (innovation / médical)
    "green_dark":  "#6FA82E",
    "slate":       "#1E2A38",   # texte ardoise
    "grey":        "#5B6B7B",
    "bg":          "#F4F7FA",
    "white":       "#FFFFFF",
}

# ─── Paramètres géométriques de la coquille ──────────────────────────────────

_CX, _CY      = 50.0, 90.0     # charnière (base de l'éventail), repère 0..100
_R            = 74.0           # rayon extérieur
_HALF_ANGLE   = 78.0           # demi-ouverture de l'éventail (degrés)
_N_SEG        = 9              # nombre de segments (cannelures)
_SCALLOP      = 6.0            # amplitude des festons du bord supérieur


def _rim_point(theta_deg: float, r: float = _R) -> tuple[float, float]:
    """Point du bord, theta mesuré depuis la verticale (positif vers la droite)."""
    t = math.radians(theta_deg)
    return (_CX + r * math.sin(t), _CY - r * math.cos(t))


def _segment_angles() -> list[float]:
    a0, a1 = -_HALF_ANGLE, _HALF_ANGLE
    return [a0 + (a1 - a0) * i / _N_SEG for i in range(_N_SEG + 1)]


# ─── Génération SVG ───────────────────────────────────────────────────────────

def build_svg() -> str:
    angles = _segment_angles()
    rim = [_rim_point(a) for a in angles]

    # Contour : charnière → bord festonné → retour charnière
    d = [f"M {_CX:.2f} {_CY:.2f}", f"L {rim[0][0]:.2f} {rim[0][1]:.2f}"]
    for i in range(_N_SEG):
        # arc bombé vers l'extérieur entre rim[i] et rim[i+1]
        x2, y2 = rim[i + 1]
        rr = _R + _SCALLOP
        d.append(f"A {rr:.2f} {rr:.2f} 0 0 1 {x2:.2f} {y2:.2f}")
    d.append("Z")
    outline = " ".join(d)

    # Nervures (de la charnière vers chaque point interne du bord)
    ridges = []
    for a in angles[1:-1]:
        rx, ry = _rim_point(a, _R - 3)
        ridges.append(
            f'<line x1="{_CX:.2f}" y1="{_CY:.2f}" x2="{rx:.2f}" y2="{ry:.2f}" '
            f'stroke="#FFFFFF" stroke-width="1.6" stroke-linecap="round" '
            f'stroke-opacity="0.55"/>'
        )
    ridges_svg = "\n    ".join(ridges)

    # Oreilles/charnière : petit demi-disque à la base
    hinge = (f'<circle cx="{_CX:.2f}" cy="{_CY:.2f}" r="7" '
             f'fill="{COLORS["blue_dark"]}"/>')

    return f"""<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"
     width="100" height="100" role="img" aria-label="CHU Toulouse">
  <defs>
    <linearGradient id="chuShell" x1="0" y1="0" x2="1" y2="0.25">
      <stop offset="0%"  stop-color="{COLORS['blue']}"/>
      <stop offset="50%" stop-color="{COLORS['teal']}"/>
      <stop offset="100%" stop-color="{COLORS['green']}"/>
    </linearGradient>
  </defs>
  <path d="{outline}" fill="url(#chuShell)"
        stroke="{COLORS['blue_dark']}" stroke-width="1.2"
        stroke-linejoin="round"/>
    {ridges_svg}
  {hinge}
</svg>
"""


def write_svg(path: str | Path = "assets/logo_chu.svg") -> Path:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(build_svg(), encoding="utf-8")
    return p


# ─── Rendu Pillow (en-tête GUI, sans dépendance SVG) ──────────────────────────

def _hex(h: str) -> tuple[int, int, int]:
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))  # type: ignore


def render_logo(size: int = 160):
    """
    Retourne une image Pillow RGBA (carrée, `size`×`size`) de la coquille,
    dégradé horizontal bleu→teal→vert masqué par la silhouette + nervures.
    Rendu en super-échantillonnage ×4 puis réduit pour des bords nets.
    """
    from PIL import Image, ImageDraw

    ss = 4
    S = size * ss
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))

    sc = S / 100.0  # échelle repère 0..100 → pixels

    def P(x, y):
        return (x * sc, y * sc)

    # Silhouette (polygone : charnière + bord festonné échantillonné finement)
    angles = _segment_angles()
    poly = [P(_CX, _CY)]
    samples = 160
    a0, a1 = angles[0], angles[-1]
    for k in range(samples + 1):
        a = a0 + (a1 - a0) * k / samples
        # ondulation du bord (festons) : amplitude _SCALLOP modulée
        phase = (a - a0) / (a1 - a0) * _N_SEG
        bump = _SCALLOP * abs(math.sin(phase * math.pi))
        x, y = _rim_point(a, _R + bump - _SCALLOP * 0.5)
        poly.append(P(x, y))
    poly.append(P(_CX, _CY))

    # Dégradé horizontal bleu→teal→vert
    grad = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    gpx = grad.load()
    c_blue, c_teal, c_green = _hex(COLORS["blue"]), _hex(COLORS["teal"]), _hex(COLORS["green"])
    for x in range(S):
        f = x / max(S - 1, 1)
        if f < 0.5:
            t = f / 0.5
            col = tuple(int(c_blue[i] + (c_teal[i] - c_blue[i]) * t) for i in range(3))
        else:
            t = (f - 0.5) / 0.5
            col = tuple(int(c_teal[i] + (c_green[i] - c_teal[i]) * t) for i in range(3))
        for y in range(S):
            gpx[x, y] = (col[0], col[1], col[2], 255)

    # Masque silhouette
    mask = Image.new("L", (S, S), 0)
    ImageDraw.Draw(mask).polygon(poly, fill=255)
    img.paste(grad, (0, 0), mask)

    # Nervures blanches translucides
    draw = ImageDraw.Draw(img)
    for a in angles[1:-1]:
        rx, ry = _rim_point(a, _R - 3)
        draw.line([P(_CX, _CY), P(rx, ry)],
                  fill=(255, 255, 255, 140), width=max(int(1.6 * sc), 1))

    # Contour
    draw.line(poly, fill=(*_hex(COLORS["blue_dark"]), 230), width=max(int(1.2 * sc), 1))
    # Charnière
    r = 7 * sc
    cx, cy = P(_CX, _CY)
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(*_hex(COLORS["blue_dark"]), 255))

    return img.resize((size, size), Image.LANCZOS)


if __name__ == "__main__":
    p = write_svg()
    print("SVG écrit →", p)
    try:
        render_logo(256).save("assets/logo_chu_preview.png")
        print("PNG aperçu → assets/logo_chu_preview.png")
    except Exception as e:
        print("Rendu Pillow indisponible :", e)
