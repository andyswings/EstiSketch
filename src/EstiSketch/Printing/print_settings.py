"""Data model for print / PDF plot settings. No GTK dependency."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
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


LINE_WEIGHT_CATEGORIES: Tuple[Tuple[str, str, float], ...] = (
    ("walls_outline", "Walls / Accents", 1.0),
    ("openings", "Doors & Windows", 0.75),
    ("fixtures", "Fixtures & Cabinetry", 0.60),
    ("stairs", "Stairs & Railings", 0.70),
    ("rooms", "Rooms & Openings", 0.50),
    ("floor_patterns", "Floor Patterns", 0.30),
    ("dimensions", "Dimensions & Leaders", 0.45),
    ("roofs", "Roofs", 0.85),
    ("footers", "Footings", 0.75),
    ("drafting", "Polylines, Circles & Arcs", 0.65),
)

LINE_WEIGHT_PRESETS: Dict[str, Dict[str, float]] = {
    "Standard AIA": {
        "global_multiplier": 1.0,
        "walls_outline": 1.0,
        "openings": 0.75,
        "fixtures": 0.60,
        "stairs": 0.70,
        "rooms": 0.50,
        "floor_patterns": 0.30,
        "dimensions": 0.45,
        "roofs": 0.85,
        "footers": 0.75,
        "drafting": 0.65,
    },
    "Fine (Small Scale)": {
        "global_multiplier": 0.65,
        "walls_outline": 0.85,
        "openings": 0.60,
        "fixtures": 0.50,
        "stairs": 0.55,
        "rooms": 0.40,
        "floor_patterns": 0.25,
        "dimensions": 0.35,
        "roofs": 0.70,
        "footers": 0.60,
        "drafting": 0.50,
    },
    "Bold (Presentation)": {
        "global_multiplier": 1.40,
        "walls_outline": 1.35,
        "openings": 0.95,
        "fixtures": 0.75,
        "stairs": 0.90,
        "rooms": 0.65,
        "floor_patterns": 0.40,
        "dimensions": 0.55,
        "roofs": 1.10,
        "footers": 0.95,
        "drafting": 0.80,
    },
    "Legacy Uniform": {
        "global_multiplier": 1.0,
        "walls_outline": 1.0,
        "openings": 1.0,
        "fixtures": 1.10,
        "stairs": 1.0,
        "rooms": 1.0,
        "floor_patterns": 0.60,
        "dimensions": 1.0,
        "roofs": 3.0,
        "footers": 2.0,
        "drafting": 1.0,
    },
}


def _clamp_float(val: object, lo: float, hi: float, default: float) -> float:
    try:
        num = float(val)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default
    return max(lo, min(hi, num))


@dataclass
class LineWeights:
    """Per-object-type print pen weights in PostScript points (1/72 in)."""

    preset: str = "Standard AIA"
    global_multiplier: float = 1.0
    walls_outline: float = 1.0
    openings: float = 0.75
    fixtures: float = 0.60
    stairs: float = 0.70
    rooms: float = 0.50
    floor_patterns: float = 0.30
    dimensions: float = 0.45
    roofs: float = 0.85
    footers: float = 0.75
    drafting: float = 0.65

    def apply_preset(self, preset_name: str) -> None:
        """Apply a named preset from ``LINE_WEIGHT_PRESETS``."""
        spec = LINE_WEIGHT_PRESETS.get(preset_name)
        if spec is None:
            return
        self.preset = preset_name
        self.global_multiplier = float(spec["global_multiplier"])
        for key, _label, default_pt in LINE_WEIGHT_CATEGORIES:
            setattr(self, key, float(spec.get(key, default_pt)))

    def width_pt(self, category: str, factor: float = 1.0) -> float:
        """Return effective stroke width in PostScript points for ``category``."""
        base = float(getattr(self, category, 0.75))
        mult = max(0.05, float(self.global_multiplier))
        return max(0.05, base * mult * float(factor))

    @classmethod
    def from_dict(cls, data: Optional[dict]) -> "LineWeights":
        """Deserialize ``LineWeights`` with clamping and defaults for older files."""
        lw = cls()
        if not isinstance(data, dict):
            return lw
        preset = data.get("preset")
        if isinstance(preset, str) and (preset in LINE_WEIGHT_PRESETS or preset == "Custom"):
            lw.preset = preset
        if "global_multiplier" in data:
            lw.global_multiplier = _clamp_float(data["global_multiplier"], 0.1, 5.0, 1.0)
        for key, _label, default_pt in LINE_WEIGHT_CATEGORIES:
            if key in data:
                setattr(lw, key, _clamp_float(data[key], 0.05, 10.0, default_pt))
        return lw


def resolve_stroke_width(
    canvas: object,
    category: str,
    screen_px: float,
    scale: float,
    factor: float = 1.0,
) -> float:
    """Return user-space stroke width (model inches) for interactive or print passes.

    During interactive drawing ``canvas._print_line_weights`` is ``None`` and this
    returns ``screen_px / scale`` unchanged. During ``printing=True`` it converts the
    configured PostScript point weight via ``lw.width_pt(category, factor) / scale``.
    """
    denom = max(float(scale), 1e-6)
    lw = getattr(canvas, "_print_line_weights", None)
    if isinstance(lw, LineWeights):
        return lw.width_pt(category, factor) / denom
    return float(screen_px) / denom


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
    line_weights: LineWeights = field(default_factory=LineWeights)
    tile_enabled: bool = False
    tile_overlap_in: float = 0.5
    tile_registration_marks: bool = True
    tile_page_numbers: bool = True

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
            elif key == "line_weights" and isinstance(value, dict):
                s.line_weights = LineWeights.from_dict(value)
            elif key in ("tile_enabled", "tile_registration_marks", "tile_page_numbers"):
                setattr(s, key, bool(value))
            elif key not in ("title_block", "line_weights") and hasattr(s, key):
                setattr(s, key, value)
        s.tile_overlap_in = _clamp_float(s.tile_overlap_in, 0.0, 2.0, 0.5)
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
