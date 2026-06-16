"""
scenario.py — Modèle de données du scénario (contrat Couche 1 ↔ Couche 2).

Un scénario est un dossier :

    <SCENARIOS_DIR>/<nom>/
        scenario.json      ← métadonnées + liste d'actions
        anchors/000.png     ← imagette template capturée avant chaque action
        anchors/001.png
        ...

Chaque `Action` porte le tempo enregistré (`delta`, secondes depuis l'action
précédente) pour rejouer à la cadence d'origine, et un `Anchor` optionnel
(template visuel) qui permet à la Couche 2 de re-localiser la cible même si
l'UI s'est déplacée (DPI, RDP, fenêtre repositionnée).
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

SCENARIO_FILE = "scenario.json"
ANCHORS_SUBDIR = "anchors"

# Types d'action reconnus par la Couche 2.
CLICK_TYPES = ("click", "double_click", "right_click", "middle_click")
ALL_TYPES = CLICK_TYPES + ("move", "scroll", "key", "text", "wait")


@dataclass
class Anchor:
    """Ancre visuelle : imagette template + position de référence à l'enregistrement."""
    template: str            # chemin relatif du PNG dans anchors/ (ex. "anchors/003.png")
    region: list[int]        # [x, y, w, h] : boîte du template sur l'écran enregistré
    click_offset: list[int]  # [dx, dy] : point d'action relatif au coin haut-gauche du template
    screen_size: list[int]   # [W, H] : résolution écran à l'enregistrement (adaptation DPI/RDP)

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(d: dict | None) -> "Anchor | None":
        if not d:
            return None
        return Anchor(
            template=d["template"],
            region=list(d["region"]),
            click_offset=list(d.get("click_offset", [0, 0])),
            screen_size=list(d.get("screen_size", [0, 0])),
        )


@dataclass
class Action:
    """Une action atomique enregistrée."""
    index: int
    type: str                       # cf. ALL_TYPES
    delta: float = 0.0              # secondes écoulées depuis l'action précédente
    x: int | None = None
    y: int | None = None
    button: str | None = None       # "left" | "right" | "middle"
    text: str | None = None         # pour type == "text"
    key: str | None = None          # pour type == "key"
    scroll_dx: int = 0
    scroll_dy: int = 0
    anchor: Anchor | None = None

    def to_dict(self) -> dict:
        d = asdict(self)
        d["anchor"] = self.anchor.to_dict() if self.anchor else None
        return d

    @staticmethod
    def from_dict(d: dict) -> "Action":
        return Action(
            index=d["index"],
            type=d["type"],
            delta=float(d.get("delta", 0.0)),
            x=d.get("x"),
            y=d.get("y"),
            button=d.get("button"),
            text=d.get("text"),
            key=d.get("key"),
            scroll_dx=int(d.get("scroll_dx", 0)),
            scroll_dy=int(d.get("scroll_dy", 0)),
            anchor=Anchor.from_dict(d.get("anchor")),
        )


@dataclass
class Scenario:
    """Un scénario complet : métadonnées + actions."""
    name: str
    created_at: str                       # ISO 8601 UTC
    screen_size: list[int]                # [W, H] à l'enregistrement
    actions: list[Action] = field(default_factory=list)
    schema_version: int = 1

    # ─── Sérialisation ───────────────────────────────────────────────────────
    def to_dict(self) -> dict:
        return {
            "schema_version": self.schema_version,
            "name": self.name,
            "created_at": self.created_at,
            "screen_size": self.screen_size,
            "actions": [a.to_dict() for a in self.actions],
        }

    def save(self, scenarios_dir: Path) -> Path:
        """Écrit scenario.json dans <scenarios_dir>/<name>/ (crée le dossier)."""
        folder = Path(scenarios_dir) / self.name
        (folder / ANCHORS_SUBDIR).mkdir(parents=True, exist_ok=True)
        path = folder / SCENARIO_FILE
        path.write_text(
            json.dumps(self.to_dict(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        return path

    @staticmethod
    def load(folder: Path) -> "Scenario":
        """Charge un scénario depuis son dossier (contenant scenario.json)."""
        folder = Path(folder)
        data = json.loads((folder / SCENARIO_FILE).read_text(encoding="utf-8"))
        return Scenario(
            name=data["name"],
            created_at=data["created_at"],
            screen_size=list(data.get("screen_size", [0, 0])),
            actions=[Action.from_dict(a) for a in data.get("actions", [])],
            schema_version=int(data.get("schema_version", 1)),
        )

    @staticmethod
    def folder_for(scenarios_dir: Path, name: str) -> Path:
        return Path(scenarios_dir) / name
