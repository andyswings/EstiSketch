"""Data model for print / PDF plot settings. No GTK dependency."""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Tuple

# Paper sizes in PostScript points (1/72"), portrait (width, height).
_IN = 72.0
_MM = 72.0 / 25.4
PAPER_SIZES: Dict[str, Tuple[float, float]] = {
    "Letter (8.5 x 11 in)": (8.5 * _IN, 11 * _IN),
    "Legal (8.5 x 14 in)": (8.5 * _IN, 14 * _IN),
    "Tabloid / ANSI B (11 x 17 in)": (11 * _IN, 17 * _IN),
    "A4 (210 x 297 mm)": (210 * _MM, 297 * _MM),
    "A3 (297 x 420 mm)": (297 * _MM, 420 * _MM),
    "A2 (420 x 594 mm)": (420 * _MM, 594 * _MM),
    "A1 (594 x 841 mm)": (594 * _MM, 841 * _MM),
    "A0 (841 x 1189 mm)": (841 * _MM, 1189 * _MM),
    "ANSI C (17 x 22 in)": (17 * _IN, 22 * _IN),
    "ANSI D (22 x 34 in)": (22 * _IN, 34 * _IN),
    "ANSI E (34 x 44 in)": (34 * _IN, 44 * _IN),
    "Arch C (18 x 24 in)": (18 * _IN, 24 * _IN),
    "Arch D (24 x 36 in)": (24 * _IN, 36 * _IN),
    "Arch E (36 x 48 in)": (36 * _IN, 48 * _IN),
}
DEFAULT_PAPER = "Letter (8.5 x 11 in)"

FIT_SCALE = "Fit to page"


def _arch(paper_inches_per_foot: float) -> float:
    """Points per model inch for 'x paper inches = 1 model foot'."""
    return paper_inches_per_foot * _IN / 12.0


# name -> points per model inch (None = fit to page)
SCALES: Dict[str, Optional[float]] = {
    FIT_SCALE: None,
    '1/16" = 1\'-0"': _arch(1 / 16),
    '3/32" = 1\'-0"': _arch(3 / 32),
    '1/8" = 1\'-0"': _arch(1 / 8),
    '3/16" = 1\'-0"': _arch(3 / 16),
    '1/4" = 1\'-0"': _arch(1 / 4),
    '3/8" = 1\'-0"': _arch(3 / 8),
    '1/2" = 1\'-0"': _arch(1 / 2),
    '3/4" = 1\'-0"': _arch(3 / 4),
    '1" = 1\'-0"': _arch(1),
    '1 1/2" = 1\'-0"': _arch(1.5),
    '3" = 1\'-0"': _arch(3),
    "1:200": _IN / 200,
    "1:100": _IN / 100,
    "1:50": _IN / 50,
    "1:20": _IN / 20,
    "1:10": _IN / 10,
}


@dataclass
class TitleBlock:
    enabled: bool = True
    company: str = ""
    project_name: str = ""
    address: str = ""
    client: str = ""
    job_number: str = ""
    drawn_by: str = ""
    checked_by: str = ""
    date: str = ""  # empty = today's date at plot time
    revision: str = ""
    drawing_title: str = ""  # e.g. "Floor Plan"; level name is appended
    sheet_prefix: str = "A"  # sheet numbers: A-1, A-2, ...


@dataclass
class PrintSettings:
    paper: str = DEFAULT_PAPER
    landscape: bool = True
    margin_in: float = 0.5
    scale_name: str = FIT_SCALE
    offset_x: float = 0.0  # manual nudge in points, relative to centered
    offset_y: float = 0.0
    draw_border: bool = True
    print_all_levels: bool = True
    level_ids: List[str] = field(default_factory=list)  # used when not all
    hidden_layer_ids: List[str] = field(default_factory=list)
    title_block: TitleBlock = field(default_factory=TitleBlock)

    # -- serialization ----------------------------------------------------
    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Optional[dict]) -> "PrintSettings":
        s = cls()
        if not isinstance(data, dict):
            return s
        for key, value in data.items():
            if key == "title_block" and isinstance(value, dict):
                for tk, tv in value.items():
                    if hasattr(s.title_block, tk):
                        setattr(s.title_block, tk, tv)
            elif key != "title_block" and hasattr(s, key):
                setattr(s, key, value)
        if s.paper not in PAPER_SIZES:
            s.paper = DEFAULT_PAPER
        if s.scale_name not in SCALES:
            s.scale_name = FIT_SCALE
        return s

    # -- derived values ---------------------------------------------------
    def page_size(self) -> Tuple[float, float]:
        w, h = PAPER_SIZES.get(self.paper, PAPER_SIZES[DEFAULT_PAPER])
        return (h, w) if self.landscape else (w, h)

    def pts_per_inch(self) -> Optional[float]:
        return SCALES.get(self.scale_name)
