"""Sanity checks that flag impossible or inconsistent results."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Dict, List

from .engine import TakeoffResult


@dataclass
class Check:
    name: str
    test: Callable[[Dict[str, float], TakeoffResult], str]  # returns "" if ok, else message
    severity: str = "warning"


@dataclass
class CheckResult:
    name: str
    severity: str
    message: str


def run_checks(checks: List[Check], measurements: Dict[str, float], result: TakeoffResult) -> List[CheckResult]:
    out = [CheckResult(r.item.id, "error", r.error) for r in result.results if r.error]
    out += [CheckResult(r.item.id, "warning", "override is stale (computed value changed)")
            for r in result.results if r.stale]
    for c in checks:
        msg = c.test(measurements, result)
        if msg:
            out.append(CheckResult(c.name, c.severity, msg))
    return out
