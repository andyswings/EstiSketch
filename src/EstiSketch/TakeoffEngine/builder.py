"""Unified full-house takeoff builder, runner, and export helpers."""
from __future__ import annotations

import csv
import json
from typing import Any, Dict, List, Optional, Tuple

from .assumptions import AssumptionSet
from .checks import Check, CheckResult, run_checks
from .engine import TakeoffEngine, TakeoffResult
from .exterior import EXTERIOR_DEFAULTS, exterior_checks, exterior_items
from .fasteners import FASTENER_DEFAULTS, fastener_items
from .foundation import FOUNDATION_DEFAULTS, form_board_check, foundation_checks, foundation_items
from .interior import INTERIOR_DEFAULTS, interior_checks, interior_items
from .line_item import LineItem
from .measurements import plan_measurements
from .roof import ROOF_DEFAULTS, roof_checks, roof_items
from .wall_framing import WALL_DEFAULTS, wall_framing_checks, wall_framing_items

ALL_DEFAULTS: Dict[str, float] = {
    **FOUNDATION_DEFAULTS,
    **WALL_DEFAULTS,
    **EXTERIOR_DEFAULTS,
    **ROOF_DEFAULTS,
    **INTERIOR_DEFAULTS,
    **FASTENER_DEFAULTS,
}


def default_items() -> List[LineItem]:
    """All built-in takeoff line items in construction-phase order."""
    return (
        foundation_items()
        + wall_framing_items()
        + exterior_items()
        + roof_items()
        + interior_items()
        + fastener_items()
    )


def default_checks(assumptions: AssumptionSet) -> List[Check]:
    """All built-in sanity checks."""
    return (
        foundation_checks()
        + [form_board_check(assumptions)]
        + wall_framing_checks(assumptions)
        + exterior_checks()
        + roof_checks(assumptions)
        + interior_checks(assumptions)
    )


def create_engine(
    project_assumptions: Optional[Dict[str, float]] = None,
    overrides: Optional[Dict[str, Dict[str, float]]] = None,
    extra_items: Optional[List[LineItem]] = None,
) -> TakeoffEngine:
    """Construct a full-house TakeoffEngine with defaults, optional project assumptions, and overrides."""
    assumptions = AssumptionSet(ALL_DEFAULTS)
    for k, v in (project_assumptions or {}).items():
        assumptions.set_project(k, float(v))
    items = default_items() + list(extra_items or [])
    engine = TakeoffEngine(items, assumptions)
    if overrides:
        engine.load_overrides(overrides)
    return engine


def run_takeoff(
    plan: Any,
    assumptions: Optional[AssumptionSet] = None,
    overrides: Optional[Dict[str, Dict[str, float]]] = None,
    extra_items: Optional[List[LineItem]] = None,
) -> Tuple[TakeoffResult, List[CheckResult], Dict[str, Any]]:
    """Compute measurements, all line items, and all checks for a plan."""
    if assumptions is None:
        assumptions = AssumptionSet(ALL_DEFAULTS)
    snap_in = assumptions.get("dimension_snap_in")
    measurements = plan_measurements(plan, snap_in=snap_in)
    engine = TakeoffEngine(default_items() + list(extra_items or []), assumptions)
    if overrides:
        engine.load_overrides(overrides)
    result = engine.compute(measurements)
    checks = run_checks(default_checks(assumptions), measurements, result)
    return result, checks, measurements


def export_takeoff_csv(result: TakeoffResult, path: str) -> None:
    """Export a TakeoffResult to a spreadsheet-friendly CSV file."""
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "Category", "ID", "Qty", "Unit", "Description",
            "Computed", "Override", "Stale", "Explanation", "Error",
        ])
        for r in result.results:
            writer.writerow([
                r.item.category,
                r.item.id,
                r.final,
                r.item.unit,
                r.item.description,
                r.computed,
                "" if r.override is None else r.override,
                "yes" if r.stale else "",
                r.item.explanation,
                r.error or "",
            ])


def export_takeoff_json(result: TakeoffResult, checks: Optional[List[CheckResult]] = None, path: Optional[str] = None) -> str:
    """Serialize a TakeoffResult (and optional checks) to JSON; writes to `path` if given."""
    payload = {
        "items": [
            {
                "id": r.item.id,
                "category": r.item.category,
                "description": r.item.description,
                "unit": r.item.unit,
                "raw": r.raw,
                "computed": r.computed,
                "override": r.override,
                "final": r.final,
                "stale": r.stale,
                "explanation": r.item.explanation,
                "error": r.error,
            }
            for r in result.results
        ],
        "checks": [
            {"name": c.name, "severity": c.severity, "message": c.message}
            for c in (checks or [])
        ],
    }
    text = json.dumps(payload, indent=2)
    if path:
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
    return text
