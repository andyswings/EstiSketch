"""Pure-Python catalog, snapping, surface resolution, and kitchen/vanity layout helpers.

Kept free of GTK/Cairo so geometry, snapping, packing, and takeoff helpers
can be unit-tested headlessly.
"""
import math
from typing import Dict, List, Optional, Tuple

from .geometry.arc_wall import arc_wall_project, arc_wall_tangent, is_curved_wall

COUNTERTOP_MATERIALS = [
    "quartz",
    "granite",
    "laminate",
    "butcher_block",
    "marble",
    "concrete",
    "solid_surface",
]

MOUNT_SURFACES = [
    "auto",
    "floor",
    "slab",
    "wall",
    "countertop",
]

FIXTURE_CATEGORIES = [
    ("kitchen_cabinet", "Kitchen Cabinets"),
    ("bathroom_vanity", "Bath Vanities"),
    ("bathroom_fixture", "Bath & Plumbing"),
    ("kitchen_appliance", "Kitchen Appliances"),
    ("laundry_appliance", "Laundry Appliances"),
    ("mechanical_utility", "HVAC & Mechanical"),
    ("living_furniture", "Living Room Furniture"),
    ("bedroom_furniture", "Bedroom Furniture"),
    ("dining_furniture", "Dining Furniture"),
    ("office_furniture", "Office Furniture"),
]

FURNITURE_CATEGORIES = {
    "living_furniture",
    "bedroom_furniture",
    "dining_furniture",
    "office_furniture",
}

# Standard AIA dimensions in model inches
FIXTURE_CATALOG: Dict[str, Dict] = {
    # ── Kitchen Cabinets ──
    "base_cabinet": {
        "label": "Base Cabinet",
        "category": "kitchen_cabinet",
        "width": 24.0,
        "depth": 24.0,
        "height": 34.5,
        "elevation": 0.0,
        "mount_surface": "auto",
        "has_countertop": True,
        "countertop_overhang": 1.5,
        "is_upper": False,
        "short_tag": "B",
    },
    "base_drawer_cabinet": {
        "label": "Drawer Base Cabinet",
        "category": "kitchen_cabinet",
        "width": 24.0,
        "depth": 24.0,
        "height": 34.5,
        "elevation": 0.0,
        "mount_surface": "auto",
        "has_countertop": True,
        "countertop_overhang": 1.5,
        "is_upper": False,
        "short_tag": "DB",
    },
    "sink_base_cabinet": {
        "label": "Sink Base Cabinet",
        "category": "kitchen_cabinet",
        "width": 36.0,
        "depth": 24.0,
        "height": 34.5,
        "elevation": 0.0,
        "mount_surface": "auto",
        "has_countertop": True,
        "countertop_overhang": 1.5,
        "is_upper": False,
        "short_tag": "SB",
    },
    "corner_base_cabinet": {
        "label": "Corner Base Cabinet",
        "category": "kitchen_cabinet",
        "width": 36.0,
        "depth": 36.0,
        "height": 34.5,
        "elevation": 0.0,
        "mount_surface": "auto",
        "has_countertop": True,
        "countertop_overhang": 1.5,
        "is_upper": False,
        "short_tag": "CB",
    },
    "upper_cabinet": {
        "label": "Upper Wall Cabinet",
        "category": "kitchen_cabinet",
        "width": 24.0,
        "depth": 12.0,
        "height": 30.0,
        "elevation": 54.0,
        "mount_surface": "wall",
        "has_countertop": False,
        "countertop_overhang": 0.0,
        "is_upper": True,
        "short_tag": "W",
    },
    "corner_upper_cabinet": {
        "label": "Corner Upper Cabinet",
        "category": "kitchen_cabinet",
        "width": 24.0,
        "depth": 24.0,
        "height": 30.0,
        "elevation": 54.0,
        "mount_surface": "wall",
        "has_countertop": False,
        "countertop_overhang": 0.0,
        "is_upper": True,
        "short_tag": "CW",
    },
    "tall_pantry": {
        "label": "Tall Pantry Cabinet",
        "category": "kitchen_cabinet",
        "width": 24.0,
        "depth": 24.0,
        "height": 84.0,
        "elevation": 0.0,
        "mount_surface": "auto",
        "has_countertop": False,
        "countertop_overhang": 0.0,
        "is_upper": False,
        "short_tag": "TP",
    },
    "island_cabinet": {
        "label": "Kitchen Island Base",
        "category": "kitchen_cabinet",
        "width": 72.0,
        "depth": 36.0,
        "height": 34.5,
        "elevation": 0.0,
        "mount_surface": "auto",
        "has_countertop": True,
        "countertop_overhang": 12.0,
        "is_upper": False,
        "short_tag": "ISL",
    },
    # ── Bath Vanities ──
    "vanity_single": {
        "label": "Single Bath Vanity",
        "category": "bathroom_vanity",
        "width": 36.0,
        "depth": 21.0,
        "height": 32.0,
        "elevation": 0.0,
        "mount_surface": "auto",
        "has_countertop": True,
        "countertop_overhang": 1.0,
        "is_upper": False,
        "short_tag": "VAN",
    },
    "vanity_double": {
        "label": "Double Bath Vanity",
        "category": "bathroom_vanity",
        "width": 60.0,
        "depth": 21.0,
        "height": 32.0,
        "elevation": 0.0,
        "mount_surface": "auto",
        "has_countertop": True,
        "countertop_overhang": 1.0,
        "is_upper": False,
        "short_tag": "2VAN",
    },
    # ── Bath & Plumbing ──
    "toilet": {
        "label": "Toilet (Water Closet)",
        "category": "bathroom_fixture",
        "width": 18.0,
        "depth": 28.0,
        "height": 29.0,
        "elevation": 0.0,
        "mount_surface": "auto",
        "has_countertop": False,
        "countertop_overhang": 0.0,
        "is_upper": False,
        "short_tag": "WC",
    },
    "bathtub": {
        "label": "Bathtub (60x30)",
        "category": "bathroom_fixture",
        "width": 60.0,
        "depth": 30.0,
        "height": 18.0,
        "elevation": 0.0,
        "mount_surface": "auto",
        "has_countertop": False,
        "countertop_overhang": 0.0,
        "is_upper": False,
        "short_tag": "TUB",
    },
    "shower_square": {
        "label": "Shower Enclosure (36x36)",
        "category": "bathroom_fixture",
        "width": 36.0,
        "depth": 36.0,
        "height": 80.0,
        "elevation": 0.0,
        "mount_surface": "auto",
        "has_countertop": False,
        "countertop_overhang": 0.0,
        "is_upper": False,
        "short_tag": "SHWR",
    },
    "shower_corner": {
        "label": "Corner Neo-Angle Shower",
        "category": "bathroom_fixture",
        "width": 38.0,
        "depth": 38.0,
        "height": 80.0,
        "elevation": 0.0,
        "mount_surface": "auto",
        "has_countertop": False,
        "countertop_overhang": 0.0,
        "is_upper": False,
        "short_tag": "SHWR",
    },
    "pedestal_sink": {
        "label": "Pedestal / Lavatory Sink",
        "category": "bathroom_fixture",
        "width": 22.0,
        "depth": 19.0,
        "height": 34.0,
        "elevation": 0.0,
        "mount_surface": "auto",
        "has_countertop": False,
        "countertop_overhang": 0.0,
        "is_upper": False,
        "short_tag": "LAV",
    },
    "kitchen_sink_single": {
        "label": "Kitchen Sink (Single Bowl)",
        "category": "bathroom_fixture",
        "width": 25.0,
        "depth": 22.0,
        "height": 9.0,
        "elevation": 34.5,
        "mount_surface": "countertop",
        "has_countertop": False,
        "countertop_overhang": 0.0,
        "is_upper": False,
        "short_tag": "KS1",
    },
    "kitchen_sink_double": {
        "label": "Kitchen Sink (Double Bowl)",
        "category": "bathroom_fixture",
        "width": 33.0,
        "depth": 22.0,
        "height": 9.0,
        "elevation": 34.5,
        "mount_surface": "countertop",
        "has_countertop": False,
        "countertop_overhang": 0.0,
        "is_upper": False,
        "short_tag": "KS2",
    },
    "utility_sink": {
        "label": "Laundry / Utility Sink",
        "category": "bathroom_fixture",
        "width": 24.0,
        "depth": 22.0,
        "height": 34.0,
        "elevation": 0.0,
        "mount_surface": "auto",
        "has_countertop": False,
        "countertop_overhang": 0.0,
        "is_upper": False,
        "short_tag": "US",
    },
    # ── Kitchen Appliances ──
    "refrigerator": {
        "label": "Refrigerator",
        "category": "kitchen_appliance",
        "width": 36.0,
        "depth": 30.0,
        "height": 70.0,
        "elevation": 0.0,
        "mount_surface": "auto",
        "has_countertop": False,
        "countertop_overhang": 0.0,
        "is_upper": False,
        "short_tag": "REF",
    },
    "range_stove": {
        "label": "Range / Stove (30\")",
        "category": "kitchen_appliance",
        "width": 30.0,
        "depth": 26.0,
        "height": 36.0,
        "elevation": 0.0,
        "mount_surface": "auto",
        "has_countertop": False,
        "countertop_overhang": 0.0,
        "is_upper": False,
        "short_tag": "RNG",
    },
    "cooktop": {
        "label": "Drop-In Cooktop",
        "category": "kitchen_appliance",
        "width": 30.0,
        "depth": 21.0,
        "height": 4.0,
        "elevation": 34.5,
        "mount_surface": "countertop",
        "has_countertop": False,
        "countertop_overhang": 0.0,
        "is_upper": False,
        "short_tag": "CT",
    },
    "wall_oven": {
        "label": "Built-In Wall Oven",
        "category": "kitchen_appliance",
        "width": 30.0,
        "depth": 24.0,
        "height": 50.0,
        "elevation": 24.0,
        "mount_surface": "wall",
        "has_countertop": False,
        "countertop_overhang": 0.0,
        "is_upper": False,
        "short_tag": "OVEN",
    },
    "dishwasher": {
        "label": "Dishwasher (24\")",
        "category": "kitchen_appliance",
        "width": 24.0,
        "depth": 24.0,
        "height": 34.0,
        "elevation": 0.0,
        "mount_surface": "auto",
        "has_countertop": True,
        "countertop_overhang": 1.5,
        "is_upper": False,
        "short_tag": "DW",
    },
    "range_hood": {
        "label": "Range Hood",
        "category": "kitchen_appliance",
        "width": 30.0,
        "depth": 20.0,
        "height": 18.0,
        "elevation": 64.0,
        "mount_surface": "wall",
        "has_countertop": False,
        "countertop_overhang": 0.0,
        "is_upper": True,
        "short_tag": "HOOD",
    },
    "microwave": {
        "label": "Over-Range Microwave",
        "category": "kitchen_appliance",
        "width": 24.0,
        "depth": 16.0,
        "height": 14.0,
        "elevation": 54.0,
        "mount_surface": "wall",
        "has_countertop": False,
        "countertop_overhang": 0.0,
        "is_upper": True,
        "short_tag": "MW",
    },
    # ── Laundry Appliances ──
    "washer": {
        "label": "Clothes Washer",
        "category": "laundry_appliance",
        "width": 27.0,
        "depth": 30.0,
        "height": 38.0,
        "elevation": 0.0,
        "mount_surface": "auto",
        "has_countertop": False,
        "countertop_overhang": 0.0,
        "is_upper": False,
        "short_tag": "W",
    },
    "dryer": {
        "label": "Clothes Dryer",
        "category": "laundry_appliance",
        "width": 27.0,
        "depth": 30.0,
        "height": 38.0,
        "elevation": 0.0,
        "mount_surface": "auto",
        "has_countertop": False,
        "countertop_overhang": 0.0,
        "is_upper": False,
        "short_tag": "D",
    },
    # ── HVAC & Mechanical ──
    "water_heater": {
        "label": "Water Heater",
        "category": "mechanical_utility",
        "width": 22.0,
        "depth": 22.0,
        "height": 60.0,
        "elevation": 0.0,
        "mount_surface": "auto",
        "has_countertop": False,
        "countertop_overhang": 0.0,
        "is_upper": False,
        "short_tag": "WH",
    },
    "furnace": {
        "label": "Furnace / Air Handler",
        "category": "mechanical_utility",
        "width": 24.0,
        "depth": 28.0,
        "height": 48.0,
        "elevation": 0.0,
        "mount_surface": "auto",
        "has_countertop": False,
        "countertop_overhang": 0.0,
        "is_upper": False,
        "short_tag": "FURN",
    },
    "air_conditioner": {
        "label": "A/C Condenser Unit",
        "category": "mechanical_utility",
        "width": 30.0,
        "depth": 30.0,
        "height": 34.0,
        "elevation": 0.0,
        "mount_surface": "auto",
        "has_countertop": False,
        "countertop_overhang": 0.0,
        "is_upper": False,
        "short_tag": "A/C",
    },
    # ── Living Room Furniture ──
    "sofa": {
        "label": "Sofa (3-Seat)",
        "category": "living_furniture",
        "width": 84.0,
        "depth": 36.0,
        "height": 34.0,
        "elevation": 0.0,
        "mount_surface": "auto",
        "has_countertop": False,
        "countertop_overhang": 0.0,
        "is_upper": False,
        "short_tag": "SOFA",
    },
    "loveseat": {
        "label": "Loveseat (2-Seat)",
        "category": "living_furniture",
        "width": 60.0,
        "depth": 36.0,
        "height": 34.0,
        "elevation": 0.0,
        "mount_surface": "auto",
        "has_countertop": False,
        "countertop_overhang": 0.0,
        "is_upper": False,
        "short_tag": "LOVE",
    },
    "armchair": {
        "label": "Armchair",
        "category": "living_furniture",
        "width": 34.0,
        "depth": 34.0,
        "height": 34.0,
        "elevation": 0.0,
        "mount_surface": "auto",
        "has_countertop": False,
        "countertop_overhang": 0.0,
        "is_upper": False,
        "short_tag": "CHR",
    },
    "coffee_table": {
        "label": "Coffee Table",
        "category": "living_furniture",
        "width": 48.0,
        "depth": 24.0,
        "height": 18.0,
        "elevation": 0.0,
        "mount_surface": "auto",
        "has_countertop": False,
        "countertop_overhang": 0.0,
        "is_upper": False,
        "short_tag": "CT",
    },
    "end_table": {
        "label": "End Table",
        "category": "living_furniture",
        "width": 22.0,
        "depth": 22.0,
        "height": 24.0,
        "elevation": 0.0,
        "mount_surface": "auto",
        "has_countertop": False,
        "countertop_overhang": 0.0,
        "is_upper": False,
        "short_tag": "ET",
    },
    "tv_console": {
        "label": "TV / Media Console",
        "category": "living_furniture",
        "width": 60.0,
        "depth": 18.0,
        "height": 24.0,
        "elevation": 0.0,
        "mount_surface": "auto",
        "has_countertop": False,
        "countertop_overhang": 0.0,
        "is_upper": False,
        "short_tag": "TV",
    },
    # ── Bedroom Furniture ──
    "bed_king": {
        "label": "King Bed",
        "category": "bedroom_furniture",
        "width": 76.0,
        "depth": 80.0,
        "height": 24.0,
        "elevation": 0.0,
        "mount_surface": "auto",
        "has_countertop": False,
        "countertop_overhang": 0.0,
        "is_upper": False,
        "short_tag": "KING",
    },
    "bed_queen": {
        "label": "Queen Bed",
        "category": "bedroom_furniture",
        "width": 60.0,
        "depth": 80.0,
        "height": 24.0,
        "elevation": 0.0,
        "mount_surface": "auto",
        "has_countertop": False,
        "countertop_overhang": 0.0,
        "is_upper": False,
        "short_tag": "QUEEN",
    },
    "bed_twin": {
        "label": "Twin Bed",
        "category": "bedroom_furniture",
        "width": 39.0,
        "depth": 75.0,
        "height": 24.0,
        "elevation": 0.0,
        "mount_surface": "auto",
        "has_countertop": False,
        "countertop_overhang": 0.0,
        "is_upper": False,
        "short_tag": "TWIN",
    },
    "nightstand": {
        "label": "Nightstand",
        "category": "bedroom_furniture",
        "width": 22.0,
        "depth": 18.0,
        "height": 24.0,
        "elevation": 0.0,
        "mount_surface": "auto",
        "has_countertop": False,
        "countertop_overhang": 0.0,
        "is_upper": False,
        "short_tag": "NS",
    },
    "dresser": {
        "label": "Dresser",
        "category": "bedroom_furniture",
        "width": 54.0,
        "depth": 20.0,
        "height": 34.0,
        "elevation": 0.0,
        "mount_surface": "auto",
        "has_countertop": False,
        "countertop_overhang": 0.0,
        "is_upper": False,
        "short_tag": "DRS",
    },
    # ── Dining Furniture ──
    "dining_table": {
        "label": "Dining Table (6-Seat)",
        "category": "dining_furniture",
        "width": 72.0,
        "depth": 36.0,
        "height": 30.0,
        "elevation": 0.0,
        "mount_surface": "auto",
        "has_countertop": False,
        "countertop_overhang": 0.0,
        "is_upper": False,
        "short_tag": "DIN",
    },
    "dining_chair": {
        "label": "Dining Chair",
        "category": "dining_furniture",
        "width": 18.0,
        "depth": 18.0,
        "height": 34.0,
        "elevation": 0.0,
        "mount_surface": "auto",
        "has_countertop": False,
        "countertop_overhang": 0.0,
        "is_upper": False,
        "short_tag": "DC",
    },
    # ── Office Furniture ──
    "desk": {
        "label": "Office Desk",
        "category": "office_furniture",
        "width": 60.0,
        "depth": 30.0,
        "height": 30.0,
        "elevation": 0.0,
        "mount_surface": "auto",
        "has_countertop": False,
        "countertop_overhang": 0.0,
        "is_upper": False,
        "short_tag": "DESK",
    },
    "office_chair": {
        "label": "Office Chair",
        "category": "office_furniture",
        "width": 24.0,
        "depth": 24.0,
        "height": 38.0,
        "elevation": 0.0,
        "mount_surface": "auto",
        "has_countertop": False,
        "countertop_overhang": 0.0,
        "is_upper": False,
        "short_tag": "OC",
    },
    "bookshelf": {
        "label": "Bookshelf",
        "category": "office_furniture",
        "width": 36.0,
        "depth": 12.0,
        "height": 72.0,
        "elevation": 0.0,
        "mount_surface": "auto",
        "has_countertop": False,
        "countertop_overhang": 0.0,
        "is_upper": False,
        "short_tag": "BKSH",
    },
}

LAYOUT_PRESETS = [
    ("one_wall", "One-Wall Kitchen"),
    ("galley", "Galley Kitchen"),
    ("l_shaped", "L-Shaped Kitchen"),
    ("u_shaped", "U-Shaped Kitchen"),
    ("g_shaped", "G-Shaped Kitchen"),
    ("peninsula", "Peninsula Kitchen"),
    ("island", "Island Kitchen"),
    ("vanity_single", "Single Bath Vanity"),
    ("vanity_double", "Double Bath Vanity"),
]


def get_fixture_spec(symbol_type: str) -> Dict:
    """Return catalog specification dict for ``symbol_type`` (falls back to ``base_cabinet``)."""
    return FIXTURE_CATALOG.get(symbol_type, FIXTURE_CATALOG["base_cabinet"])


def _point_in_poly(px: float, py: float, pts: List[Tuple[float, float]]) -> bool:
    if not pts or len(pts) < 3:
        return False
    inside = False
    n = len(pts)
    for i in range(n):
        x1, y1 = pts[i]
        x2, y2 = pts[(i + 1) % n]
        if ((y1 > py) != (y2 > py)) and (px < (x2 - x1) * (py - y1) / (y2 - y1 + 1e-18) + x1):
            inside = not inside
    return inside


def resolve_fixture_surface(fixture, rooms) -> Tuple[str, float]:
    """Resolve whether ``fixture`` rests on a concrete slab or standard floor and set ``base_elevation``."""
    mount = getattr(fixture, "mount_surface", "auto") or "auto"
    fx = float(getattr(fixture, "x", 0.0))
    fy = float(getattr(fixture, "y", 0.0))

    enclosing_room = None
    for room in rooms or []:
        if getattr(room, "visible", True) is False:
            continue
        if _point_in_poly(fx, fy, getattr(room, "points", [])):
            enclosing_room = room
            break

    slab_elev = 0.0
    if enclosing_room is not None and getattr(enclosing_room, "is_slab", False):
        slab_elev = float(getattr(enclosing_room, "slab_thickness", 4.0) or 4.0)

    if mount == "slab":
        elev = slab_elev if slab_elev > 0 else float(getattr(fixture, "base_elevation", 4.0) or 4.0)
        fixture.base_elevation = elev
        return ("slab", elev)
    if mount == "auto":
        if slab_elev > 0:
            fixture.base_elevation = slab_elev
            return ("slab", slab_elev)
        fixture.base_elevation = 0.0
        return ("floor", 0.0)
    if mount in ("wall", "countertop"):
        fixture.base_elevation = slab_elev
        return (mount, slab_elev)
    fixture.base_elevation = 0.0
    return ("floor", 0.0)


def _collect_wall_candidates(
    x: float,
    y: float,
    depth: float,
    walls,
    snap_dist: float,
):
    """Collect nearby straight/curved wall face candidates sorted by snap score."""
    candidates = []
    for wall in walls or []:
        if getattr(wall, "symbolic", False):
            continue
        w_width = float(getattr(wall, "width", 0.0) or 0.0)
        if is_curved_wall(wall):
            ratio, dist_cl, closest = arc_wall_project(wall, (x, y))
            tx, ty = arc_wall_tangent(wall, ratio)
            seg_len = float(getattr(wall, "arc_radius", 100.0) or 100.0) * math.pi
        else:
            x1, y1 = wall.start
            x2, y2 = wall.end
            dx, dy = x2 - x1, y2 - y1
            len_sq = dx * dx + dy * dy
            if len_sq <= 1e-9:
                continue
            seg_len = math.sqrt(len_sq)
            tx, ty = dx / seg_len, dy / seg_len
            t = max(0.0, min(1.0, ((x - x1) * dx + (y - y1) * dy) / len_sq))
            closest = (x1 + t * dx, y1 + t * dy)
            dist_cl = math.hypot(x - closest[0], y - closest[1])

        face_edge_dist = abs(dist_cl - w_width / 2.0)
        face_center_dist = abs(dist_cl - (w_width / 2.0 + depth / 2.0))
        min_d = min(dist_cl, face_edge_dist, face_center_dist)
        if min_d > snap_dist:
            continue

        nx, ny = -ty, tx
        side_dot = (x - closest[0]) * nx + (y - closest[1]) * ny
        sign = 1.0 if side_dot >= 0.0 else -1.0
        out_nx, out_ny = sign * nx, sign * ny
        # Prefer real structural walls (w_width > 0) slightly over virtual room-edge fallbacks
        score = min_d + (0.5 if w_width <= 0.0 else 0.0)
        candidates.append((score, min_d, closest, (out_nx, out_ny), w_width, (tx, ty), wall))

    candidates.sort(key=lambda item: item[0])
    return candidates


def _intersect_inner_faces(c1, n1, w1: float, c2, n2, w2: float) -> Optional[Tuple[float, float]]:
    """Intersect inner-face offset lines of two nearly perpendicular walls."""
    det = n1[0] * n2[1] - n1[1] * n2[0]
    if abs(det) < 0.15:
        return None
    q1x, q1y = c1[0] + n1[0] * (w1 / 2.0), c1[1] + n1[1] * (w1 / 2.0)
    q2x, q2y = c2[0] + n2[0] * (w2 / 2.0), c2[1] + n2[1] * (w2 / 2.0)
    d1 = n1[0] * q1x + n1[1] * q1y
    d2 = n2[0] * q2x + n2[1] * q2y
    return ((d1 * n2[1] - n1[1] * d2) / det, (n1[0] * d2 - d1 * n2[0]) / det)


def _corner_axes_from_normals(n1, n2) -> Tuple[Tuple[float, float], Tuple[float, float], float]:
    """Order two inward perpendicular wall normals into right-handed (local_x, local_y, rot_deg)."""
    if n1[0] * n2[1] - n1[1] * n2[0] > 0.0:
        lx, ly = n1, n2
    else:
        lx, ly = n2, n1
    rot_deg = math.degrees(math.atan2(lx[1], lx[0])) % 360.0
    return lx, ly, rot_deg


def _angle_diff_deg(a: float, b: float) -> float:
    return abs(((a - b + 180.0) % 360.0) - 180.0)


def snap_fixture_to_walls(
    x: float,
    y: float,
    width: float,
    depth: float,
    walls,
    snap_dist: float = 24.0,
    current_rotation: float = 0.0,
    symbol_type: str = "",
) -> Tuple[float, float, float, Optional[object]]:
    """Snap fixture back edge flush against nearest wall(s) or inside corner and orient front into room."""
    is_corner = symbol_type in ("corner_base_cabinet", "corner_upper_cabinet")
    candidates = _collect_wall_candidates(x, y, depth, walls, snap_dist)
    if not candidates:
        return (x, y, float(current_rotation) % 360.0, None)

    _, _, c1, n1, w1, t1, wall1 = candidates[0]
    corner_reach = max(width, depth) * 0.75 + snap_dist

    # Check if a second perpendicular wall forms an inside corner near (x, y)
    for _, _, c2, n2, w2, _t2, _wall2 in candidates[1:]:
        if abs(n1[0] * n2[0] + n1[1] * n2[1]) >= 0.15:
            continue
        p_corner = _intersect_inner_faces(c1, n1, w1, c2, n2, w2)
        if p_corner is None:
            continue
        if math.hypot(p_corner[0] - c1[0], p_corner[1] - c1[1]) > corner_reach:
            continue
        if math.hypot(p_corner[0] - c2[0], p_corner[1] - c2[1]) > corner_reach:
            continue
        if is_corner:
            lx, ly, rot_deg = _corner_axes_from_normals(n1, n2)
            sx = p_corner[0] + lx[0] * (width / 2.0) + ly[0] * (depth / 2.0)
            sy = p_corner[1] + lx[1] * (width / 2.0) + ly[1] * (depth / 2.0)
            return (sx, sy, rot_deg, wall1)
        # Regular cabinet: flush back against primary wall1 and check if side edge sits near wall2
        rot_deg = math.degrees(math.atan2(-n1[0], n1[1])) % 360.0
        q1x, q1y = c1[0] + n1[0] * (w1 / 2.0), c1[1] + n1[1] * (w1 / 2.0)
        # Distance from corner along wall1's tangent toward wall2's inward half-space
        along = (x - p_corner[0]) * n2[0] + (y - p_corner[1]) * n2[1]
        if 0.0 <= along <= width / 2.0 + snap_dist * 0.6:
            sx = p_corner[0] + n1[0] * (depth / 2.0) + n2[0] * (width / 2.0)
            sy = p_corner[1] + n1[1] * (depth / 2.0) + n2[1] * (width / 2.0)
            return (sx, sy, rot_deg, wall1)

    wall_rot = math.degrees(math.atan2(-n1[0], n1[1])) % 360.0
    if is_corner:
        # Two valid orientations put one wing's back edge flush against wall1
        alt_rot = (wall_rot + 90.0) % 360.0
        cur = float(current_rotation) % 360.0
        if _angle_diff_deg(alt_rot, cur) < _angle_diff_deg(wall_rot, cur):
            rot_deg = alt_rot
            offset = w1 / 2.0 + width / 2.0
        else:
            rot_deg = wall_rot
            offset = w1 / 2.0 + depth / 2.0
    else:
        rot_deg = wall_rot
        offset = w1 / 2.0 + depth / 2.0

    sx = c1[0] + n1[0] * offset
    sy = c1[1] + n1[1] * offset
    return (sx, sy, rot_deg, wall1)


def snap_point_to_wall_face(
    x: float,
    y: float,
    walls,
    snap_dist: float = 18.0,
) -> Tuple[float, float, Optional[Tuple[float, float]]]:
    """Project point ``(x, y)`` onto nearest wall inner face (or inside corner) and return inward normal."""
    candidates = _collect_wall_candidates(x, y, 0.0, walls, snap_dist)
    if not candidates:
        return (x, y, None)
    _, _, c1, n1, w1, _t1, _wall1 = candidates[0]
    for _, _, c2, n2, w2, _t2, _wall2 in candidates[1:]:
        if abs(n1[0] * n2[0] + n1[1] * n2[1]) >= 0.15:
            continue
        p_corner = _intersect_inner_faces(c1, n1, w1, c2, n2, w2)
        if p_corner is not None and math.hypot(p_corner[0] - x, p_corner[1] - y) <= snap_dist * 1.35:
            return (p_corner[0], p_corner[1], n1)
    fx = c1[0] + n1[0] * (w1 / 2.0)
    fy = c1[1] + n1[1] * (w1 / 2.0)
    return (fx, fy, n1)


def snap_layout_to_walls(
    layout_type: str,
    origin: Tuple[float, float],
    rotation_deg: float,
    walls,
    snap_dist: float = 24.0,
) -> Tuple[Tuple[float, float], float, bool]:
    """Snap a kitchen or vanity layout's anchor origin/orientation flush against a room corner or wall face."""
    ox, oy = float(origin[0]), float(origin[1])
    candidates = _collect_wall_candidates(ox, oy, 24.0, walls, snap_dist)
    if not candidates:
        return (origin, float(rotation_deg) % 360.0, False)

    _, _, c1, n1, w1, _t1, _wall1 = candidates[0]
    if layout_type in ("l_shaped", "u_shaped", "g_shaped", "peninsula"):
        for _, _, c2, n2, w2, _t2, _wall2 in candidates[1:]:
            if abs(n1[0] * n2[0] + n1[1] * n2[1]) >= 0.15:
                continue
            p_corner = _intersect_inner_faces(c1, n1, w1, c2, n2, w2)
            if p_corner is None:
                continue
            if math.hypot(p_corner[0] - ox, p_corner[1] - oy) <= 36.0 + snap_dist:
                _lx, _ly, rot_deg = _corner_axes_from_normals(n1, n2)
                return (p_corner, rot_deg, True)

    fx = c1[0] + n1[0] * (w1 / 2.0)
    fy = c1[1] + n1[1] * (w1 / 2.0)
    rot_deg = math.degrees(math.atan2(-n1[0], n1[1])) % 360.0
    return ((fx, fy), rot_deg, True)


def _modular_widths(total_len: float, min_width: float = 6.0) -> List[float]:
    """Split ``total_len`` into standard cabinet widths (36, 30, 24, 18, 15, 12)."""
    widths: List[float] = []
    rem = float(total_len)
    if rem < min_width - 1e-6:
        return widths
    standards = (36.0, 30.0, 24.0, 18.0, 15.0, 12.0)
    while rem >= 12.0 - 1e-4:
        picked = None
        for sw in standards:
            if rem - sw >= -1e-4:
                leftover = rem - sw
                if leftover < 1e-4 or leftover >= min_width - 1e-4:
                    picked = sw
                    break
        if picked is None:
            break
        widths.append(picked)
        rem -= picked
    if rem >= min_width - 1e-4:
        widths.append(round(rem, 2))
    return widths


def _make_fixture(
    symbol_type: str,
    x: float,
    y: float,
    rotation: float = 0.0,
    width: Optional[float] = None,
    depth: Optional[float] = None,
    countertop_material: str = "quartz",
    layer_id: str = "",
    has_countertop: Optional[bool] = None,
    existing_ids: Optional[List[str]] = None,
):
    from .components import Fixture, generate_identifier

    spec = get_fixture_spec(symbol_type)
    ident = generate_identifier("fixture", existing_ids)
    if existing_ids is not None:
        existing_ids.append(ident)
    ct_flag = spec["has_countertop"] if has_countertop is None else bool(has_countertop)
    return Fixture(
        symbol_type=symbol_type,
        x=x,
        y=y,
        width=float(width if width is not None else spec["width"]),
        depth=float(depth if depth is not None else spec["depth"]),
        height=float(spec["height"]),
        rotation=float(rotation) % 360.0,
        elevation=float(spec["elevation"]),
        mount_surface=spec["mount_surface"],
        has_countertop=ct_flag,
        countertop_overhang=float(spec["countertop_overhang"]) if ct_flag else 0.0,
        countertop_material=countertop_material,
        identifier=ident,
        layer_id=layer_id,
    )


def pack_cabinet_run(
    start: Tuple[float, float],
    end: Tuple[float, float],
    include_uppers: bool = True,
    countertop_material: str = "quartz",
    layer_id: str = "",
    depth: float = 24.0,
    side: float = 1.0,
    existing_ids: Optional[List[str]] = None,
) -> List[object]:
    """Generate modular base (and optional upper) cabinets along a run line ``start -> end``."""
    dx = end[0] - start[0]
    dy = end[1] - start[1]
    run_len = math.hypot(dx, dy)
    if run_len < 6.0:
        return []
    ux, uy = dx / run_len, dy / run_len
    s_sign = 1.0 if side >= 0.0 else -1.0
    # Normal pointing toward front (+Y local)
    nx, ny = -uy * s_sign, ux * s_sign
    rot_deg = math.degrees(math.atan2(-nx, ny)) % 360.0

    widths = _modular_widths(run_len)
    out = []
    pos = 0.0
    for w in widths:
        cx_line = start[0] + ux * (pos + w / 2.0)
        cy_line = start[1] + uy * (pos + w / 2.0)
        bx = cx_line + nx * (depth / 2.0)
        by = cy_line + ny * (depth / 2.0)
        out.append(
            _make_fixture(
                "base_cabinet",
                bx,
                by,
                rotation=rot_deg,
                width=w,
                depth=depth,
                countertop_material=countertop_material,
                layer_id=layer_id,
                existing_ids=existing_ids,
            )
        )
        if include_uppers:
            upper_d = 12.0
            ux_pos = cx_line + nx * (upper_d / 2.0)
            uy_pos = cy_line + ny * (upper_d / 2.0)
            out.append(
                _make_fixture(
                    "upper_cabinet",
                    ux_pos,
                    uy_pos,
                    rotation=rot_deg,
                    width=w,
                    depth=upper_d,
                    countertop_material=countertop_material,
                    layer_id=layer_id,
                    existing_ids=existing_ids,
                )
            )
        pos += w
    return out


def _fill_run_slots(
    length: float,
    appliances: List[Tuple[str, float]],
    fill_type: str = "base_cabinet",
) -> List[Tuple[str, float]]:
    """Interleave requested appliances into a run of ``length`` and fill remaining space with modular cabinets."""
    total_app = sum(w for _, w in appliances)
    if total_app > length:
        appliances = []
        total_app = 0.0

    rem = max(0.0, length - total_app)
    if not appliances:
        return [(fill_type, w) for w in _modular_widths(length)]

    # Split remaining cabinet width evenly into slots around appliances
    slots_count = len(appliances) + 1
    per_slot = rem / slots_count
    result: List[Tuple[str, float]] = []
    acc_rem = rem
    for idx, (app_type, app_w) in enumerate(appliances):
        slot_target = round(per_slot, 1) if idx < len(appliances) else acc_rem
        slot_target = min(slot_target, acc_rem)
        for cw in _modular_widths(slot_target, min_width=9.0):
            result.append((fill_type, cw))
            acc_rem -= cw
        result.append((app_type, app_w))
    for cw in _modular_widths(acc_rem):
        result.append((fill_type, cw))
    return result


def generate_kitchen_or_vanity_layout(
    layout_type: str,
    origin: Tuple[float, float],
    rotation_deg: float = 0.0,
    run_a: float = 120.0,
    run_b: float = 108.0,
    include_uppers: bool = True,
    include_appliances: bool = True,
    countertop_material: str = "quartz",
    layer_id: str = "",
    existing_ids: Optional[List[str]] = None,
) -> List[object]:
    """Build an individually-editable kitchen or bath vanity layout anchored at ``origin``."""
    items_local: List[Tuple[str, float, float, float, Optional[float], Optional[float]]] = []
    base_d = 24.0
    upper_d = 12.0

    def add_straight_run(start_x: float, start_y: float, ux: float, uy: float, length: float, specs: List[Tuple[str, float]]):
        # ux, uy = unit tangent along run; outward front normal for +X run is (0, +1) -> ny = ux, nx = -uy
        nx, ny = -uy, ux
        r_deg = math.degrees(math.atan2(-nx, ny)) % 360.0
        pos = 0.0
        for sym, w in specs:
            if pos + w > length + 1e-4:
                break
            spec = get_fixture_spec(sym)
            d = float(spec["depth"])
            cx = start_x + ux * (pos + w / 2.0) + nx * (d / 2.0)
            cy = start_y + uy * (pos + w / 2.0) + ny * (d / 2.0)
            items_local.append((sym, cx, cy, r_deg, w, d))
            if include_uppers:
                if sym in ("base_cabinet", "base_drawer_cabinet", "sink_base_cabinet"):
                    items_local.append((
                        "upper_cabinet",
                        start_x + ux * (pos + w / 2.0) + nx * (upper_d / 2.0),
                        start_y + uy * (pos + w / 2.0) + ny * (upper_d / 2.0),
                        r_deg,
                        w,
                        upper_d,
                    ))
                elif sym == "range_stove":
                    items_local.append((
                        "range_hood",
                        start_x + ux * (pos + w / 2.0) + nx * (10.0),
                        start_y + uy * (pos + w / 2.0) + ny * (10.0),
                        r_deg,
                        w,
                        20.0,
                    ))
            pos += w

    run_a = max(36.0, float(run_a))
    run_b = max(36.0, float(run_b))

    if layout_type == "vanity_single":
        items_local.append(("vanity_single", 18.0, 10.5, 0.0, 36.0, 21.0))
    elif layout_type == "vanity_double":
        items_local.append(("vanity_double", 30.0, 10.5, 0.0, 60.0, 21.0))
    elif layout_type == "one_wall":
        apps = [("refrigerator", 36.0), ("sink_base_cabinet", 36.0), ("dishwasher", 24.0), ("range_stove", 30.0)] if include_appliances else []
        while apps and sum(w for _, w in apps) > run_a:
            apps.pop()
        specs = _fill_run_slots(run_a, apps)
        add_straight_run(0.0, 0.0, 1.0, 0.0, run_a, specs)
    elif layout_type == "galley":
        top_apps = [("sink_base_cabinet", 36.0), ("dishwasher", 24.0)] if include_appliances else []
        bot_apps = [("refrigerator", 36.0), ("range_stove", 30.0)] if include_appliances else []
        while top_apps and sum(w for _, w in top_apps) > run_a:
            top_apps.pop()
        while bot_apps and sum(w for _, w in bot_apps) > run_a:
            bot_apps.pop()
        aisle = 48.0
        add_straight_run(0.0, 0.0, 1.0, 0.0, run_a, _fill_run_slots(run_a, top_apps))
        # Bottom run faces -Y (run right-to-left from x=run_a to 0 at y = aisle + 2*base_d)
        add_straight_run(run_a, aisle + 2.0 * base_d, -1.0, 0.0, run_a, _fill_run_slots(run_a, bot_apps))
    elif layout_type in ("l_shaped", "peninsula"):
        # Corner base at (18, 18) back-left (0, 0)
        items_local.append(("corner_base_cabinet", 18.0, 18.0, 0.0, 36.0, 36.0))
        if include_uppers:
            items_local.append(("corner_upper_cabinet", 12.0, 12.0, 0.0, 24.0, 24.0))
        len_x = max(24.0, run_a - 36.0)
        pen_has_corner = (layout_type == "peninsula" and run_b >= 96.0)
        len_y = max(24.0, run_b - (72.0 if pen_has_corner else 36.0))
        apps_x = [("sink_base_cabinet", 36.0), ("dishwasher", 24.0)] if include_appliances and len_x >= 60.0 else []
        apps_y = (
            [("range_stove", 30.0), ("refrigerator", 36.0)]
            if include_appliances and len_y >= 66.0
            else ([("range_stove", 30.0)] if include_appliances and len_y >= 30.0 else [])
        )
        add_straight_run(36.0, 0.0, 1.0, 0.0, len_x, _fill_run_slots(len_x, apps_x))
        # Left leg running downward from y=36..36+len_y facing +X (rot=270: tangent=(0,-1), normal=(+1,0))
        add_straight_run(0.0, 36.0 + len_y, 0.0, -1.0, len_y, _fill_run_slots(len_y, apps_y))
        if layout_type == "peninsula":
            pen_len = max(48.0, min(72.0, run_a * 0.55))
            if pen_has_corner:
                items_local.append(("corner_base_cabinet", 18.0, run_b - 18.0, 270.0, 36.0, 36.0))
                items_local.append(("island_cabinet", 36.0 + pen_len / 2.0, run_b - 12.0, 0.0, pen_len, 24.0))
            else:
                items_local.append(("island_cabinet", 24.0 + pen_len / 2.0, run_b - 12.0, 0.0, pen_len, 24.0))
    elif layout_type in ("u_shaped", "g_shaped"):
        back_w = max(96.0, run_a)
        wing_d = max(72.0, run_b)
        items_local.append(("corner_base_cabinet", 18.0, 18.0, 0.0, 36.0, 36.0))
        items_local.append(("corner_base_cabinet", back_w - 18.0, 18.0, 90.0, 36.0, 36.0))
        if include_uppers:
            items_local.append(("corner_upper_cabinet", 12.0, 12.0, 0.0, 24.0, 24.0))
            items_local.append(("corner_upper_cabinet", back_w - 12.0, 12.0, 90.0, 24.0, 24.0))
        mid_len = max(24.0, back_w - 72.0)
        leg_len_l = max(24.0, wing_d - 36.0)
        g_has_corner = (layout_type == "g_shaped" and wing_d >= 96.0)
        leg_len_r = max(24.0, wing_d - (72.0 if g_has_corner else 36.0))
        back_apps = [("sink_base_cabinet", 36.0)] if include_appliances and mid_len >= 36.0 else []
        left_apps = [("range_stove", 30.0)] if include_appliances and leg_len_l >= 30.0 else []
        right_apps = [("refrigerator", 36.0)] if include_appliances and leg_len_r >= 36.0 else []
        add_straight_run(36.0, 0.0, 1.0, 0.0, mid_len, _fill_run_slots(mid_len, back_apps))
        add_straight_run(0.0, 36.0 + leg_len_l, 0.0, -1.0, leg_len_l, _fill_run_slots(leg_len_l, left_apps))
        add_straight_run(back_w, 36.0, 0.0, 1.0, leg_len_r, _fill_run_slots(leg_len_r, right_apps))
        if layout_type == "g_shaped":
            pen_len = max(36.0, min(54.0, back_w * 0.42))
            if g_has_corner:
                items_local.append(("corner_base_cabinet", back_w - 18.0, wing_d - 18.0, 180.0, 36.0, 36.0))
                items_local.append(("island_cabinet", back_w - 36.0 - pen_len / 2.0, wing_d - 12.0, 0.0, pen_len, 24.0))
            else:
                items_local.append(("island_cabinet", back_w - 24.0 - pen_len / 2.0, wing_d - 12.0, 0.0, pen_len, 24.0))
    elif layout_type == "island":
        apps = [("refrigerator", 36.0), ("sink_base_cabinet", 36.0), ("dishwasher", 24.0), ("range_stove", 30.0)] if include_appliances else []
        while apps and sum(w for _, w in apps) > run_a:
            apps.pop()
        add_straight_run(0.0, 0.0, 1.0, 0.0, run_a, _fill_run_slots(run_a, apps))
        isl_w = max(48.0, min(84.0, run_a * 0.65))
        items_local.append(("island_cabinet", run_a / 2.0, base_d + 42.0 + 18.0, 180.0, isl_w, 36.0))
    else:
        add_straight_run(0.0, 0.0, 1.0, 0.0, run_a, _fill_run_slots(run_a, []))

    # Transform all local coordinates around origin by rotation_deg
    rad = math.radians(rotation_deg)
    ca, sa = math.cos(rad), math.sin(rad)
    ox, oy = origin
    out = []
    for sym, lx, ly, lrot, lw, ld in items_local:
        wx = ox + lx * ca - ly * sa
        wy = oy + lx * sa + ly * ca
        wrot = (lrot + rotation_deg) % 360.0
        out.append(
            _make_fixture(
                sym,
                wx,
                wy,
                rotation=wrot,
                width=lw,
                depth=ld,
                countertop_material=countertop_material,
                layer_id=layer_id,
                existing_ids=existing_ids,
            )
        )
    return out
