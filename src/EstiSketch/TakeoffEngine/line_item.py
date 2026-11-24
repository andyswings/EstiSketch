"""Line item records and evaluation."""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

# rounding modes
CEIL, ROUND, NONE = "ceil", "round", "none"


def round_qty(value: float, mode: str = CEIL) -> float:
    """Round up with a tiny epsilon so 14.0000000001 does not become 15."""
    if mode == CEIL:
        return float(math.ceil(value - 1e-9))
    if mode == ROUND:
        return float(round(value))
    return float(value)


@dataclass
class LineItem:
    """A takeoff line. `formula` receives (measurements, assumptions) and returns the raw quantity."""
    id: str
    description: str
    category: str
    unit: str
    formula: Callable[[Dict[str, float], Dict[str, float]], float]
    explanation: str = ""
    rounding: str = CEIL
    waste_pct: float = 0.0  # applied after the formula, before rounding
    requires: List[str] = field(default_factory=list)  # measurement keys needed
    enabled: bool = True
    # optional: formula returning [(key, description, qty)] rows for items whose rows depend on the plan
    multi: Optional[Callable[[Dict, Dict[str, float]], list]] = None
    hide_if_zero: bool = False


@dataclass
class LineResult:
    item: LineItem
    raw: float
    computed: float          # after waste and rounding
    override: Optional[float] = None
    stale: bool = False      # override set against an older computed value
    old_computed: Optional[float] = None
    error: Optional[str] = None

    @property
    def final(self) -> float:
        return self.override if self.override is not None else self.computed
