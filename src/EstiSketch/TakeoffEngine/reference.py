"""Reference takeoffs (hand-checked) and variance reports."""
from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from typing import Dict, List, Sequence, Tuple

from .engine import TakeoffResult


@dataclass
class ReferenceTakeoff:
    name: str
    values: Dict[str, float]                    # item_id -> hand-checked quantity
    assumptions: Dict[str, float] = field(default_factory=dict)
    computed_at_save: Dict[str, float] = field(default_factory=dict)

    def to_json(self) -> str:
        return json.dumps(self.__dict__, indent=2, sort_keys=True)

    @classmethod
    def from_json(cls, text: str) -> "ReferenceTakeoff":
        return cls(**json.loads(text))

    def save(self, path: str) -> None:
        with open(path, "w", encoding="utf-8") as f:
            f.write(self.to_json())

    @classmethod
    def load(cls, path: str) -> "ReferenceTakeoff":
        with open(path, encoding="utf-8") as f:
            return cls.from_json(f.read())


@dataclass
class VariancePoint:
    item_id: str
    engine: float
    reference: float

    @property
    def diff(self) -> float:
        return self.engine - self.reference

    @property
    def pct(self) -> float:
        return 0.0 if self.reference == 0 and self.engine == 0 else (
            float("inf") if self.reference == 0 else self.diff / self.reference * 100.0)


def compare_to_reference(result: TakeoffResult, ref: ReferenceTakeoff, use_final: bool = False) -> List[VariancePoint]:
    """Compares computed values (not overrides unless use_final) with the reference."""
    out = []
    for item_id, ref_val in ref.values.items():
        try:
            r = result.by_id(item_id)
        except KeyError:
            out.append(VariancePoint(item_id, float("nan"), ref_val))
            continue
        out.append(VariancePoint(item_id, r.final if use_final else r.computed, ref_val))
    return out


@dataclass
class CalibrationSuggestion:
    """A proposed calibration review derived from consistent variances across multiple reference jobs."""
    item_id: str
    jobs_checked: int
    mean_pct_diff: float   # positive = engine is consistently high; negative = consistently low
    direction: str         # "high" or "low"
    message: str


def suggest_calibrations(
    pairs: Sequence[Tuple[TakeoffResult, ReferenceTakeoff]],
    min_jobs: int = 3,
    threshold_pct: float = 5.0,
) -> List[CalibrationSuggestion]:
    """Propose calibration reviews (never auto-applied) when an item drifts in the same direction
    by at least `threshold_pct` across `min_jobs` or more reference takeoffs."""
    by_item: Dict[str, List[float]] = {}
    for result, ref in pairs:
        for vp in compare_to_reference(result, ref):
            if math.isnan(vp.engine) or math.isinf(vp.pct):
                continue
            by_item.setdefault(vp.item_id, []).append(vp.pct)

    suggestions: List[CalibrationSuggestion] = []
    for item_id, pcts in sorted(by_item.items()):
        if len(pcts) < min_jobs:
            continue
        all_high = all(p >= threshold_pct for p in pcts)
        all_low = all(p <= -threshold_pct for p in pcts)
        if not (all_high or all_low):
            continue
        mean_pct = sum(pcts) / len(pcts)
        direction = "high" if all_high else "low"
        suggestions.append(
            CalibrationSuggestion(
                item_id=item_id,
                jobs_checked=len(pcts),
                mean_pct_diff=mean_pct,
                direction=direction,
                message=(
                    f"{item_id} was {abs(mean_pct):.1f}% {direction} on {len(pcts)} of {len(pcts)} "
                    f"reference jobs; review its assumptions or formula"
                ),
            )
        )
    return suggestions


def item_confidence(
    pairs: Sequence[Tuple[TakeoffResult, ReferenceTakeoff]],
    tolerance_pct: float = 2.0,
) -> Dict[str, str]:
    """Return a match-history label per item_id across reference jobs (e.g. '3/3 matched')."""
    stats: Dict[str, List[bool]] = {}
    for result, ref in pairs:
        for vp in compare_to_reference(result, ref):
            if math.isnan(vp.engine) or math.isinf(vp.pct):
                stats.setdefault(vp.item_id, []).append(False)
            else:
                stats.setdefault(vp.item_id, []).append(abs(vp.pct) <= tolerance_pct)
    return {
        item_id: f"{sum(ok)}/{len(ok)} matched"
        for item_id, ok in sorted(stats.items())
    }
