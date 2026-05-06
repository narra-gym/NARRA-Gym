"""Persona loader."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

import yaml


PERSONAS_DIR = Path(__file__).resolve().parent / "personas"


@dataclass
class Persona:
    """A single user persona used to drive a simulated session."""

    id: str
    display_name: str
    raw: Dict[str, Any]
    source_path: Path

    @property
    def emotional_need(self) -> str:
        return str(self.raw.get("emotional_need", "")).strip()

    @property
    def language(self) -> str:
        return str(self.raw.get("language", "en"))

    @property
    def max_user_turns(self) -> int:
        end = self.raw.get("end_condition") or {}
        try:
            return int(end.get("max_user_turns", 12))
        except (TypeError, ValueError):
            return 12

    def card_for_prompt(self) -> str:
        """Compact JSON dump of the persona for prompt injection."""
        return json.dumps(self.raw, ensure_ascii=False, indent=2)


def load_persona(path: Path) -> Persona:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Persona file {path} did not parse to a dict.")
    persona_id = str(data.get("id") or path.stem)
    display_name = str(data.get("display_name") or persona_id)
    return Persona(id=persona_id, display_name=display_name, raw=data, source_path=path)


def discover_personas(directory: Optional[Path] = None) -> List[Persona]:
    target = directory or PERSONAS_DIR
    if not target.exists():
        return []
    personas = [load_persona(p) for p in sorted(target.glob("*.yaml"))]
    return personas


def filter_personas(personas: Iterable[Persona], ids: Optional[List[str]]) -> List[Persona]:
    if not ids:
        return list(personas)
    wanted = {i.strip() for i in ids if i.strip()}
    selected = [p for p in personas if p.id in wanted]
    missing = wanted - {p.id for p in selected}
    if missing:
        raise ValueError(f"Unknown persona id(s): {sorted(missing)}")
    return selected
