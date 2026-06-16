"""
chu_logo.py — Logo CHU de Toulouse.

Expose :
  • COLORS                : palette officielle (hex)
  • build_svg()           : retourne le SVG officiel de la coquille
  • write_svg(path)       : écrit le SVG sur disque
  • render_logo(size)     : retourne une image Pillow RGBA (en-tête GUI)

Couleurs officielles extraites du SVG CHU de Toulouse :
  dégradé radial #adce80 → #4eaf98 → #3c9aac → #006471 → #004d6b
  texte / contours : #004d6b (bleu marine)
"""

from __future__ import annotations

import math
from pathlib import Path

# ─── Palette officielle CHU de Toulouse ──────────────────────────────────────

COLORS = {
    "green_light":  "#adce80",   # vert clair (0 % du dégradé)
    "teal":         "#4eaf98",   # vert-bleu  (48.47 %)
    "blue_teal":    "#3c9aac",   # bleu-vert  (59.53 %)
    "blue_deep":    "#006471",   # bleu-vert foncé (88.64 %)
    "navy":         "#004d6b",   # bleu marine (100 % + texte/contours)
    # Aliases utilisés dans gui.py
    "blue":         "#3c9aac",
    "blue_dark":    "#004d6b",
    "green":        "#adce80",
    "green_dark":   "#006471",
    "slate":        "#004d6b",
    "grey":         "#5B6B7B",
    "bg":           "#EAF3F6",
    "white":        "#FFFFFF",
}

# ─── Silhouette officielle de la coquille (chemin SVG extrait du logo) ────────

_SHELL_PATH = (
    "M34.1514,6.2165"
    "c-3.2362-.0293-7.0807.8623-11.416,3.1572"
    "C10.6675,15.6077,6.9268,23.6774,9.4362,31.9512"
    "c1.5796,5.2617,5.5835,8.8965,9.8857,11.9707"
    "c4.3027,3.0742,8.9722,5.4883,11.7041,9.5215"
    "c.3906.5703.7334,1.1699,1.0254,1.791"
    "c.1543.333.667.2227.6582-.1426"
    "c-.042-1.8018-.0781-4.9248.9717-8.0596"
    "c1.6865-5.082,5.8452-8.2578,8.7383-12.5957"
    "c4.1074-6.126,4.6875-14.2031,1.2891-20.6504"
    "c-1.874-3.5391-5.0674-6.9893-9.3574-7.543Z"
)

_VB_W, _VB_H = 113.3858, 56.6924   # viewBox officiel


# ─── Génération SVG ───────────────────────────────────────────────────────────

def build_svg() -> str:
    navy = COLORS["navy"]
    return f"""<?xml version="1.0" encoding="utf-8"?>
<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink"
     viewBox="0 0 {_VB_W} {_VB_H}" role="img" aria-label="CHU de Toulouse">
  <defs>
    <radialGradient id="chuGradient" cx="50%" cy="50%" r="50%"
                    gradientUnits="objectBoundingBox"
                    gradientTransform="translate(0.5,0.5) rotate(-42.284) scale(1,0.989) translate(-0.5,-0.5)">
      <stop offset="0%"      stop-color="{COLORS['green_light']}"/>
      <stop offset="48.47%"  stop-color="{COLORS['teal']}"/>
      <stop offset="59.53%"  stop-color="{COLORS['blue_teal']}"/>
      <stop offset="88.64%"  stop-color="{COLORS['blue_deep']}"/>
      <stop offset="100%"    stop-color="{COLORS['navy']}"/>
    </radialGradient>
    <clipPath id="clippath-1">
      <path d="{_SHELL_PATH}"/>
    </clipPath>
  </defs>

  <g clip-path="url(#clippath-1)">
    <rect x="9.436" y="6.2165" width="42.9207" height="42.4898"
          fill="url(#chuGradient)"/>
  </g>

  <path d="{_SHELL_PATH}"
        fill="none" stroke="{navy}" stroke-width="0.5"/>

  <!-- Petits éléments graphiques à la base de la coquille -->
  <path d="M22.0254,47.0762c-.0127.0049-.0264.0059-.04.0039
           c-.6689-.1104-2.3242-1.0254-3.5664-2.4131
           c-.9229-1.0264-.9619-2.293-.6182-2.9561
           c.2197-.4189.5264-.5166.7051-.543
           c.5156-.0742,1.0938.2197,1.5879.543
           c2.2637,1.4883,2.1455,5.2656,1.9316,5.3653Z"
        fill="{navy}"/>
  <path d="M30.5596,51.5918c-.0049.0137-.0127.0254-.0234.0342
           c-.5312.4307-2.3945.877-4.0938.3174
           c-1.2285-.4082-1.8164-1.5-.8965-2.7441
           c.0283-.0391.0576-.0771.0879-.1143
           c.5791-.6953,1.627-.9805,2.5977-.8262
           c2.6914.4307,2.4961,3.1543,2.3281,3.333Z"
        fill="{navy}"/>

  <text x="60" y="22" font-family="Arial, Helvetica, sans-serif"
        font-size="16" font-weight="700" fill="{navy}" letter-spacing="1">CHU</text>
  <text x="60" y="35" font-family="Arial, Helvetica, sans-serif"
        font-size="7.5" font-weight="400" fill="{navy}" letter-spacing="2">DE</text>
  <text x="60" y="47" font-family="Arial, Helvetica, sans-serif"
        font-size="9" font-weight="400" fill="{navy}" letter-spacing="0.5">TOULOUSE</text>
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


def _lerp(a: tuple, b: tuple, t: float) -> tuple:
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def _gradient_color(f: float) -> tuple[int, int, int]:
    """Dégradé officiel : vert clair → teal → bleu-vert → bleu foncé → marine."""
    stops = [
        (0.0000, _hex(COLORS["green_light"])),
        (0.4847, _hex(COLORS["teal"])),
        (0.5953, _hex(COLORS["blue_teal"])),
        (0.8864, _hex(COLORS["blue_deep"])),
        (1.0000, _hex(COLORS["navy"])),
    ]
    for i in range(len(stops) - 1):
        t0, c0 = stops[i]
        t1, c1 = stops[i + 1]
        if t0 <= f <= t1:
            seg = (f - t0) / (t1 - t0) if t1 > t0 else 0.0
            return _lerp(c0, c1, seg)
    return stops[-1][1]


def _shell_polygon(S: int) -> list[tuple[float, float]]:
    """
    Approximation polygonale de la silhouette officielle, mise à l'échelle.
    La coquille occupe ~x:9..52, y:6..55 dans le viewBox 113x57.
    Pour le rendu carré on extrait uniquement la zone coquille.
    """
    shell_vb_x0, shell_vb_y0 = 9.0, 6.0
    shell_vb_w = 43.5
    sc = S / shell_vb_w

    def P(x: float, y: float) -> tuple[float, float]:
        return ((x - shell_vb_x0) * sc, (y - shell_vb_y0) * sc)

    return [
        P(34.15, 6.22),
        P(24.50, 7.50),
        P(15.00, 12.00),
        P(9.44,  20.00),
        P(9.44,  32.00),
        P(14.00, 40.00),
        P(19.32, 43.92),
        P(25.00, 48.50),
        P(32.04, 55.00),
        P(32.67, 54.86),
        P(33.64, 46.80),
        P(38.00, 38.50),
        P(42.50, 29.00),
        P(44.50, 20.00),
        P(43.00, 12.00),
        P(38.50, 7.50),
        P(34.15, 6.22),
    ]


def render_logo(size: int = 160):
    """
    Retourne une image Pillow RGBA (carrée, size×size) de la coquille CHU,
    avec le dégradé officiel (vert clair → marine).
    Rendu en super-échantillonnage ×4 puis réduit pour des bords nets.
    """
    from PIL import Image, ImageDraw

    ss = 4
    S = size * ss
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))

    poly = _shell_polygon(S)

    # Dégradé diagonal vert→marine (approxime le radial officiel)
    grad = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    gpx = grad.load()
    for x in range(S):
        for y in range(S):
            f = (x + y) / max(2 * S - 2, 1)
            col = _gradient_color(f)
            gpx[x, y] = (col[0], col[1], col[2], 255)

    # Masque silhouette
    mask = Image.new("L", (S, S), 0)
    ImageDraw.Draw(mask).polygon(poly, fill=255)
    img.paste(grad, (0, 0), mask)

    # Contour bleu marine
    draw = ImageDraw.Draw(img)
    navy_rgba = (*_hex(COLORS["navy"]), 230)
    draw.line(poly, fill=navy_rgba, width=max(int(1.2 * S / 100), 1))

    return img.resize((size, size), Image.LANCZOS)


if __name__ == "__main__":
    p = write_svg()
    print("SVG écrit →", p)
    try:
        render_logo(256).save("assets/logo_chu_preview.png")
        print("PNG aperçu → assets/logo_chu_preview.png")
    except Exception as e:
        print("Rendu Pillow indisponible :", e)
