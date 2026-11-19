"""Evaluates line items, tracks overrides and stale state."""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Dict, List, Optional

from .assumptions import AssumptionSet
from .line_item import LineItem, LineResult, round_qty


@dataclass
class TakeoffResult:
    results: List[LineResult] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def by_id(self, item_id: str) -> LineResult:
        for r in self.results:
            if r.item.id == item_id:
                return r
        raise KeyError(item_id)

    def by_category(self) -> Dict[str, List[LineResult]]:
        out: Dict[str, List[LineResult]] = {}
        for r in self.results:
            out.setdefault(r.item.category, []).append(r)
        return out


class TakeoffEngine:
    def __init__(self, items: List[LineItem], assumptions: AssumptionSet):
        self.items = list(items)
        self.assumptions = assumptions
        # item_id -> {"value": float, "computed_at_override": float}
        self.overrides: Dict[str, Dict[str, float]] = {}

    def set_override(self, item_id: str, value: float, current_computed: float) -> None:
        self.overrides[item_id] = {"value": float(value), "computed_at_override": float(current_computed)}

    def clear_override(self, item_id: str) -> None:
        self.overrides.pop(item_id, None)

    def keep_override(self, item_id: str, new_computed: float) -> None:
        """Accept a stale override: record the new computed value as its baseline."""
        if item_id in self.overrides:
            self.overrides[item_id]["computed_at_override"] = float(new_computed)

    def _expand(self, item: LineItem, measurements, res: TakeoffResult) -> List[LineItem]:
        """Turn a multi-row item into one concrete item per row (ids are `item:key`)."""
        try:
            rows = item.multi(measurements, self.assumptions.resolve_all(item.id))
        except Exception as exc:
            res.results.append(LineResult(item, 0.0, 0.0, error=str(exc)))
            return []
        out = []
        for key, desc, qty in rows:
            out.append(replace(item, id=f"{item.id}:{key}", description=desc, multi=None,
                               formula=(lambda m, a, q=qty: q), requires=[]))
        return out

    def compute(self, measurements: Dict[str, float]) -> TakeoffResult:
        res = TakeoffResult()
        for base_item in self.items:
            if not base_item.enabled:
                continue
            missing = [k for k in base_item.requires if k not in measurements]
            if base_item.multi is not None and not missing:
                batch = self._expand(base_item, measurements, res)
            else:
                batch = [base_item]
            for item in batch:
                missing = [k for k in item.requires if k not in measurements]
                if missing:
                    res.results.append(LineResult(item, 0.0, 0.0, error=f"missing measurements: {missing}"))
                    continue
                try:
                    raw = float(item.formula(measurements, self.assumptions.resolve_all(item.id)))
                except Exception as exc:  # surfaced to the user, never silent
                    res.results.append(LineResult(item, 0.0, 0.0, error=str(exc)))
                    continue
                computed = round_qty(raw * (1.0 + item.waste_pct / 100.0), item.rounding)
                lr = LineResult(item, raw, computed)
                ov = self.overrides.get(item.id)
                if item.hide_if_zero and computed == 0 and ov is None:
                    continue
                if ov is not None:
                    lr.override = ov["value"]
                    if abs(ov["computed_at_override"] - computed) > 1e-9:
                        lr.stale = True
                        lr.old_computed = ov["computed_at_override"]
                res.results.append(lr)
        return res

    def overrides_to_dict(self) -> dict:
        return {k: dict(v) for k, v in self.overrides.items()}

    def load_overrides(self, data: dict) -> None:
        self.overrides = {k: dict(v) for k, v in data.items()}
