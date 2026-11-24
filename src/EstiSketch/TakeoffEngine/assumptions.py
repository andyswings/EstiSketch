"""Layered, user-editable assumptions (global -> project -> item)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Optional


@dataclass
class Assumption:
    key: str
    value: float
    label: str = ""
    unit: str = ""


class AssumptionSet:
    """Resolves an assumption by item override, then project, then global default."""

    def __init__(self, defaults: Optional[Dict[str, float]] = None):
        self.global_defaults: Dict[str, float] = dict(defaults or {})
        self.project: Dict[str, float] = {}
        self.item: Dict[str, Dict[str, float]] = {}
        self.history: list = []  # versioned changes: (scope, key, old, new)

    def set_project(self, key: str, value: float) -> None:
        self.history.append(("project", key, self.project.get(key), value))
        self.project[key] = value

    def set_item(self, item_id: str, key: str, value: float) -> None:
        self.history.append((f"item:{item_id}", key, self.item.get(item_id, {}).get(key), value))
        self.item.setdefault(item_id, {})[key] = value

    def get(self, key: str, item_id: Optional[str] = None) -> float:
        if item_id and key in self.item.get(item_id, {}):
            return self.item[item_id][key]
        if key in self.project:
            return self.project[key]
        if key in self.global_defaults:
            return self.global_defaults[key]
        raise KeyError(f"Unknown assumption: {key}")

    def resolve_all(self, item_id: Optional[str] = None) -> Dict[str, float]:
        out = dict(self.global_defaults)
        out.update(self.project)
        if item_id:
            out.update(self.item.get(item_id, {}))
        return out

    def to_dict(self) -> dict:
        return {"project": dict(self.project), "item": {k: dict(v) for k, v in self.item.items()}}

    def load_dict(self, data: dict) -> None:
        self.project = dict(data.get("project", {}))
        self.item = {k: dict(v) for k, v in data.get("item", {}).items()}
