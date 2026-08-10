#!/usr/bin/env python3
"""
roof_takeoff.py

Polyline-Based Roof Material Takeoff & Inference Engine for EstiSketch.
"""

import math
import sys
import os
from dataclasses import dataclass, field
from typing import List, Tuple, Dict, Optional

# Standard Constants
CM_PER_INCH = 2.54
CM_PER_FOOT = 30.48
INCHES_PER_FOOT = 12.0
SQFT_PER_SQUARE = 100.0
BUNDLES_PER_SQUARE = 3
SYNTHETIC_UNDERLAYMENT_SQFT_PER_ROLL = 1000.0  # Standard 10-sq roll
ICE_WATER_SHIELD_SQFT_PER_ROLL = 200.0         # Standard 2-sq roll (36" x 66.7')
DRIP_EDGE_STICK_LEN_FT = 10.0
STEP_FLASHING_PCS_PER_PACK = 50                 # Standard 50-pack step flashing (4" x 4" x 8")
FASCIA_BOARD_STOCK_LEN_FT = 16.0
RIDGE_CAP_COVERAGE_LF_PER_BUNDLE = 35.0        # Standard cap shingle bundle coverage


def slope_factor(pitch_rise: float, pitch_run: float = 12.0) -> float:
    """Calculate slope factor (secant multiplier) from pitch rise/run."""
    return math.sqrt(1.0 + (pitch_rise / pitch_run) ** 2)


def infer_overhang(sketched_overhang_in: float, standard_targets_in: List[float] = [12.0, 16.0, 18.0, 24.0, 30.0], tolerance_in: float = 6.0) -> float:
    """
    Infer standard overhang (e.g. 24") from freehand or roughly sketched polyline distance.
    If sketched distance is within tolerance of a target, returns the snapped target value.
    """
    best_target = sketched_overhang_in
    min_diff = float('inf')

    for target in standard_targets_in:
        diff = abs(sketched_overhang_in - target)
        if diff <= tolerance_in and diff < min_diff:
            min_diff = diff
            best_target = target

    return best_target


@dataclass
class SketchedLine:
    """Represents a sketched polyline segment in the roof plan."""
    start: Tuple[float, float]  # (x, y) in feet
    end: Tuple[float, float]    # (x, y) in feet
    edge_type: str              # 'eave', 'ridge', 'hip', 'valley', 'rake'
    label: str = ""
    pitch_rise: float = 6.0     # Associated pitch (rise in 12)

    @property
    def length_ft(self) -> float:
        dx = self.end[0] - self.start[0]
        dy = self.end[1] - self.start[1]
        return math.hypot(dx, dy)


def select_rafter_lumber_spec(
    len_3d_ft: float,
    max_dim_len_ft: float = 20.0,
    is_hip: bool = False
) -> Dict:
    """
    Select appropriate lumber specification (Dimensional SPF vs Engineered Wood I-Joist / LVL)
    based on 3D sloped length and max dimensional lumber availability cap (20 ft).
    """
    stock_lengths = [10.0, 12.0, 14.0, 16.0, 18.0, 20.0]
    
    if len_3d_ft <= max_dim_len_ft:
        # Dimensional Lumber (SPF)
        stock_len = 20.0
        for sl in stock_lengths:
            if sl >= len_3d_ft:
                stock_len = sl
                break
        if is_hip:
            size = "2x12" if len_3d_ft > 12.0 else "2x10"
            desc = f"{size} x {stock_len:.0f}' Standard SPF Lumber"
        else:
            size = "2x10" if len_3d_ft > 12.0 else "2x8"
            desc = f"{size} x {stock_len:.0f}' Standard SPF Lumber"
        return {
            'is_engineered': False,
            'size': size,
            'stock_len_ft': stock_len,
            'desc': desc
        }
    else:
        # Exceeds max dimensional lumber length (20') -> Engineered Wood (Wood I-Joist / LVL)
        stock_len = float(math.ceil(len_3d_ft / 2.0) * 2)  # Even lengths e.g. 22', 24', 26', 28'
        if is_hip:
            size = "1-3/4\" x 11-7/8\" LVL"
            desc = f"1-3/4\" x 11-7/8\" LVL Engineered Beam x {stock_len:.0f}'"
        else:
            size = "11-7/8\" TJI"
            desc = f"11-7/8\" Engineered Wood I-Joist (TJI / Wood I-Beam) x {stock_len:.0f}'"
        return {
            'is_engineered': True,
            'size': size,
            'stock_len_ft': stock_len,
            'desc': desc
        }


@dataclass
class RoofSection:
    """
    Represents a discrete roof section (e.g., Garage Hip Roof or Main House Gable Roof).
    """
    name: str
    roof_type: str               # 'hip', 'gable', 'shed', 'offset_gable'
    pitch_rise: float = 6.0      # Rise (e.g., 6 for 6:12)
    sketched_overhang_in: float = 23.5
    footprint_width_ft: float = 24.0
    footprint_length_ft: float = 24.0
    num_eave_sides: int = 3      # 3 for 3-sided garage hip, 2 for main house gable
    tie_in: bool = False         # True if this roof ties into another roof
    framing_type: str = "truss"  # 'truss' (Engineered Trusses) or 'stick' (Stick Framed Rafters/Ridge)
    rafter_spacing_in: float = 16.0  # 16.0" OC or 24.0" OC rafter spacing
    max_dimensional_len_ft: float = 20.0  # Max dimensional lumber length cap
    use_lvl_ridge: bool = False  # True to use Engineered Wood LVL Ridge Beam

    @property
    def snapped_overhang_in(self) -> float:
        return infer_overhang(self.sketched_overhang_in)

    @property
    def snapped_overhang_ft(self) -> float:
        return self.snapped_overhang_in / INCHES_PER_FOOT

    @property
    def slope_mult(self) -> float:
        return slope_factor(self.pitch_rise, 12.0)

    @property
    def total_width_with_overhang_ft(self) -> float:
        return self.footprint_width_ft + (2.0 * self.snapped_overhang_ft)

    @property
    def total_length_with_overhang_ft(self) -> float:
        return self.footprint_length_ft + (2.0 * self.snapped_overhang_ft)

    @property
    def framing_type_normalized(self) -> str:
        ft = str(self.framing_type).lower()
        if 'stick' in ft:
            return 'stick'
        return 'truss'

    @property
    def framing_type_display(self) -> str:
        if self.framing_type_normalized == 'stick':
            return f"Stick Framed (Rafters @ {self.rafter_spacing_in:.0f}\" OC)"
        return "Engineered Trusses"

    def calculate_lines(self) -> Dict[str, float]:
        oh_ft = self.snapped_overhang_ft
        w_oh = self.footprint_width_ft + 2 * oh_ft
        l_oh = self.footprint_length_ft + (oh_ft if self.tie_in else 2 * oh_ft)

        eave_lf = 0.0
        ridge_lf = 0.0
        hip_lf = 0.0
        valley_lf = 0.0
        rake_lf = 0.0

        if self.roof_type == 'hip':
            if self.num_eave_sides == 3 and self.tie_in:
                eave_lf = w_oh + (2.0 * (self.footprint_length_ft + oh_ft))
                hip_plan_run = math.hypot(w_oh / 2.0, w_oh / 2.0)
                single_hip = math.hypot(hip_plan_run, (w_oh / 2.0) * (self.pitch_rise / 12.0))
                hip_lf = 2.0 * single_hip

                ridge_plan_len = (self.footprint_length_ft + oh_ft) - (w_oh / 2.0)
                ridge_lf = max(0.0, ridge_plan_len)

                valley_plan_run = math.hypot(w_oh / 2.0, w_oh / 2.0)
                single_valley = math.hypot(valley_plan_run, (w_oh / 2.0) * (self.pitch_rise / 12.0))
                valley_lf = 2.0 * single_valley
            else:
                eave_lf = 2.0 * w_oh + 2.0 * l_oh
                short_side = min(w_oh, l_oh)
                long_side = max(w_oh, l_oh)

                hip_plan_run = math.hypot(short_side / 2.0, short_side / 2.0)
                single_hip = math.hypot(hip_plan_run, (short_side / 2.0) * (self.pitch_rise / 12.0))
                hip_lf = 4.0 * single_hip

                ridge_lf = long_side - short_side

        elif self.roof_type == 'gable':
            eave_lf = 2.0 * l_oh
            ridge_lf = l_oh
            single_rake = (w_oh / 2.0) * self.slope_mult
            rake_lf = 4.0 * single_rake

        return {
            'eave_lf': eave_lf,
            'ridge_lf': ridge_lf,
            'hip_lf': hip_lf,
            'valley_lf': valley_lf,
            'rake_lf': rake_lf
        }

    def calculate_area_sqft(self) -> float:
        oh_ft = self.snapped_overhang_ft
        w_oh = self.footprint_width_ft + 2 * oh_ft
        l_oh = self.footprint_length_ft + (oh_ft if self.tie_in else 2 * oh_ft)
        proj_area_sqft = w_oh * l_oh
        return proj_area_sqft * self.slope_mult

    def calculate_framing_materials(self) -> Dict:
        oh_ft = self.snapped_overhang_ft
        l_oh = self.footprint_length_ft + (oh_ft if self.tie_in else 2.0 * oh_ft)
        w_oh = self.footprint_width_ft + 2.0 * oh_ft
        half_width_run = (self.footprint_width_ft / 2.0) + oh_ft

        if self.framing_type_normalized == 'truss':
            truss_spacing_ft = 2.0
            total_truss_count = math.ceil(l_oh / truss_spacing_ft) + 1

            if self.roof_type == 'gable':
                gable_end_trusses = 2
                common_trusses = max(0, total_truss_count - 2)
                hip_truss_sets = 0
            elif self.roof_type == 'hip':
                gable_end_trusses = 0
                common_trusses = max(0, total_truss_count - 4) if self.num_eave_sides == 4 else max(0, total_truss_count - 2)
                hip_truss_sets = 1
            else:
                gable_end_trusses = 0
                common_trusses = total_truss_count
                hip_truss_sets = 0

            bracing_16ft_boards = max(2, math.ceil(l_oh / 8.0) * 2)
            lines = self.calculate_lines()
            eave_lf = lines.get('eave_lf', 0.0)
            bird_blocking_16ft = math.ceil(eave_lf / 16.0) if eave_lf > 0 else 0

            fly_spec = None
            outlooker_spec = None

            if self.roof_type == 'gable' and oh_ft > 0:
                num_gable_ends = 1 if self.tie_in else 2
                fly_count = num_gable_ends * 2
                common_3d_len_ft = half_width_run * self.slope_mult
                fly_lumber_info = select_rafter_lumber_spec(common_3d_len_ft, self.max_dimensional_len_ft, is_hip=False)
                fly_spec = {
                    'count': fly_count,
                    'len_3d_ft': common_3d_len_ft,
                    'stock_len_ft': fly_lumber_info['stock_len_ft'],
                    'size': fly_lumber_info['size'],
                    'is_engineered': fly_lumber_info['is_engineered'],
                    'desc': f"{fly_lumber_info['size']} x {fly_lumber_info['stock_len_ft']:.0f}' Standard SPF Lumber (Truss Gable Fly Rafters / Barge Rafters)"
                }

                outlooker_piece_len = 3.0 * oh_ft
                single_rake = (w_oh / 2.0) * self.slope_mult
                outlookers_per_rake = math.ceil(single_rake / 2.0)
                total_outlookers = num_gable_ends * 2 * outlookers_per_rake
                boards_16ft = math.ceil((total_outlookers * outlooker_piece_len) / 16.0)

                outlooker_spec = {
                    'count': total_outlookers,
                    'piece_len_ft': outlooker_piece_len,
                    'boards_16ft': boards_16ft,
                    'size': '2x4',
                    'desc': f"2x4 x 16' Standard SPF Lumber (Truss Gable Outlookers / Outriggers - {total_outlookers} pcs @ {outlooker_piece_len:.1f}' each)"
                }

            return {
                'type': 'truss',
                'display_name': 'Engineered Trusses',
                'total_trusses': total_truss_count,
                'common_trusses': common_trusses,
                'gable_end_trusses': gable_end_trusses,
                'hip_truss_sets': hip_truss_sets,
                'bracing_16ft_boards': bracing_16ft_boards,
                'fly_rafters': fly_spec,
                'outlookers': outlooker_spec,
                'bird_blocking_16ft': bird_blocking_16ft
            }
        else:
            spacing_ft = max(0.5, self.rafter_spacing_in / 12.0)
            rafter_pairs = math.ceil(l_oh / spacing_ft) + 1

            common_3d_len_ft = half_width_run * self.slope_mult
            common_spec = select_rafter_lumber_spec(common_3d_len_ft, self.max_dimensional_len_ft, is_hip=False)

            lines = self.calculate_lines()
            ridge_lf = lines.get('ridge_lf', l_oh)

            is_lvl_ridge = self.use_lvl_ridge or (ridge_lf > self.max_dimensional_len_ft)
            if is_lvl_ridge:
                ridge_boards_count = math.ceil(ridge_lf / 16.0) if ridge_lf > 0 else 0
                ridge_spec = {
                    'is_lvl': True,
                    'count': ridge_boards_count,
                    'size': '1-3/4" x 11-7/8" LVL',
                    'desc': f"1-3/4\" x 11-7/8\" LVL Engineered Wood Ridge Beam (16' stock)"
                }
            else:
                ridge_boards_count = math.ceil(ridge_lf / 16.0) if ridge_lf > 0 else 0
                ridge_size = "2x10" if half_width_run <= 12.0 else "2x12"
                ridge_spec = {
                    'is_lvl': False,
                    'count': ridge_boards_count,
                    'size': ridge_size,
                    'desc': f"{ridge_size} x 16' Standard SPF Lumber (Roof Ridge Board)"
                }

            hip_spec = None
            valley_spec = None
            jack_spec = None

            if self.roof_type == 'hip':
                hip_plan_run = math.hypot(half_width_run, half_width_run)
                hip_3d_len_ft = math.hypot(hip_plan_run, half_width_run * (self.pitch_rise / 12.0))
                hip_lumber_info = select_rafter_lumber_spec(hip_3d_len_ft, self.max_dimensional_len_ft, is_hip=True)

                if self.num_eave_sides == 3 and self.tie_in:
                    hip_count = 2
                    valley_count = 2
                    valley_lumber_info = select_rafter_lumber_spec(hip_3d_len_ft, self.max_dimensional_len_ft, is_hip=True)
                    valley_spec = {
                        'count': valley_count,
                        'len_3d_ft': hip_3d_len_ft,
                        'stock_len_ft': valley_lumber_info['stock_len_ft'],
                        'size': valley_lumber_info['size'],
                        'is_engineered': valley_lumber_info['is_engineered'],
                        'desc': valley_lumber_info['desc']
                    }
                else:
                    hip_count = 4
                    valley_count = 0

                hip_spec = {
                    'count': hip_count,
                    'len_3d_ft': hip_3d_len_ft,
                    'stock_len_ft': hip_lumber_info['stock_len_ft'],
                    'size': hip_lumber_info['size'],
                    'is_engineered': hip_lumber_info['is_engineered'],
                    'desc': hip_lumber_info['desc']
                }

                common_pairs = math.ceil(ridge_lf / spacing_ft) + 1 if ridge_lf > 0 else 0
                common_count = common_pairs * 2

                jack_count = max(0, (rafter_pairs * 2) - common_count)
                jack_lumber_info = select_rafter_lumber_spec(common_3d_len_ft * 0.6, self.max_dimensional_len_ft, is_hip=False)
                jack_spec = {
                    'count': jack_count,
                    'stock_len_ft': jack_lumber_info['stock_len_ft'],
                    'size': jack_lumber_info['size'],
                    'is_engineered': jack_lumber_info['is_engineered'],
                    'desc': jack_lumber_info['desc']
                }
            fly_spec = None
            outlooker_spec = None

            if self.roof_type == 'gable':
                common_count = rafter_pairs * 2
                if oh_ft > 0:
                    num_gable_ends = 1 if self.tie_in else 2
                    fly_count = num_gable_ends * 2
                    fly_spec = {
                        'count': fly_count,
                        'len_3d_ft': common_3d_len_ft,
                        'stock_len_ft': common_spec['stock_len_ft'],
                        'size': common_spec['size'],
                        'is_engineered': common_spec['is_engineered'],
                        'desc': f"{common_spec['size']} x {common_spec['stock_len_ft']:.0f}' Standard SPF Lumber (Fly Rafters / Barge Rafters)"
                    }

                    outlooker_piece_len = 3.0 * oh_ft
                    single_rake = (w_oh / 2.0) * self.slope_mult
                    outlookers_per_rake = math.ceil(single_rake / 2.0)
                    total_outlookers = num_gable_ends * 2 * outlookers_per_rake
                    boards_16ft = math.ceil((total_outlookers * outlooker_piece_len) / 16.0)

                    outlooker_spec = {
                        'count': total_outlookers,
                        'piece_len_ft': outlooker_piece_len,
                        'boards_16ft': boards_16ft,
                        'size': '2x4',
                        'desc': f"2x4 x 16' Standard SPF Lumber (Gable Outlookers / Outriggers - {total_outlookers} pcs @ {outlooker_piece_len:.1f}' each)"
                    }
            else:
                common_count = rafter_pairs * 2

            common_rafter_spec = {
                'count': common_count,
                'len_3d_ft': common_3d_len_ft,
                'stock_len_ft': common_spec['stock_len_ft'],
                'size': common_spec['size'],
                'is_engineered': common_spec['is_engineered'],
                'desc': common_spec['desc']
            }

            collar_ties_12ft = math.ceil(rafter_pairs / 2.0)
            lines = self.calculate_lines()
            eave_lf = lines.get('eave_lf', 0.0)
            bird_blocking_16ft = math.ceil(eave_lf / 16.0) if eave_lf > 0 else 0
            bird_block_spec = {
                'count': bird_blocking_16ft,
                'stock_len_ft': 16.0,
                'size': '2x4' if self.rafter_spacing_in <= 16.0 else '2x6',
                'desc': f"{'2x4' if self.rafter_spacing_in <= 16.0 else '2x6'} x 16' Standard SPF Lumber (Eave Bird Blocking / Frieze Blocks)"
            }

            return {
                'type': 'stick',
                'display_name': f"Stick Framed (Rafters @ {self.rafter_spacing_in:.0f}\" OC)",
                'rafter_spacing_in': self.rafter_spacing_in,
                'max_dimensional_len_ft': self.max_dimensional_len_ft,
                'common_rafters': common_rafter_spec,
                'hip_rafters': hip_spec,
                'valley_rafters': valley_spec,
                'jack_rafters': jack_spec,
                'fly_rafters': fly_spec,
                'outlookers': outlooker_spec,
                'bird_blocking': bird_block_spec,
                'ridge_beam': ridge_spec,
                'collar_ties_12ft': collar_ties_12ft
            }


@dataclass
class CombinedRoofTakeoff:
    """Aggregates multiple roof sections into a complete bill of materials."""
    project_name: str
    sections: List[RoofSection]
    waste_percent: float = 10.0
    sheathing_thickness: str = '5/8"'
    sheathing_type: str = 'OSB'
    sheathing_sheet_width_ft: float = 4.0
    sheathing_sheet_height_ft: float = 8.0

    def generate_material_takeoff(self) -> Dict:
        total_net_area_sqft = 0.0
        total_eave_lf = 0.0
        total_ridge_lf = 0.0
        total_hip_lf = 0.0
        total_valley_lf = 0.0
        total_rake_lf = 0.0

        section_summaries = []

        total_trusses = 0
        common_trusses = 0
        gable_end_trusses = 0
        hip_truss_sets = 0
        truss_bracing_16ft = 0
        truss_fly_rafters = []
        truss_outlookers = []
        truss_bird_blocking_16ft = 0

        rafter_details = []
        collar_ties_12ft = 0

        has_truss = False
        has_stick = False

        for sec in self.sections:
            area = sec.calculate_area_sqft()
            lines = sec.calculate_lines()

            total_net_area_sqft += area
            total_eave_lf += lines['eave_lf']
            total_ridge_lf += lines['ridge_lf']
            total_hip_lf += lines['hip_lf']
            total_valley_lf += lines['valley_lf']
            total_rake_lf += lines['rake_lf']

            framing = sec.calculate_framing_materials()
            if framing['type'] == 'truss':
                has_truss = True
                total_trusses += framing['total_trusses']
                common_trusses += framing['common_trusses']
                gable_end_trusses += framing['gable_end_trusses']
                hip_truss_sets += framing['hip_truss_sets']
                truss_bracing_16ft += framing['bracing_16ft_boards']
                truss_bird_blocking_16ft += framing.get('bird_blocking_16ft', 0)

                fl = framing.get('fly_rafters')
                if fl and fl['count'] > 0:
                    truss_fly_rafters.append({
                        'section_name': sec.name,
                        'count': fl['count'],
                        'stock_len_ft': fl['stock_len_ft'],
                        'size': fl['size'],
                        'desc': fl['desc']
                    })
                ol = framing.get('outlookers')
                if ol and ol['count'] > 0:
                    truss_outlookers.append({
                        'section_name': sec.name,
                        'count': ol['count'],
                        'boards_16ft': ol['boards_16ft'],
                        'piece_len_ft': ol['piece_len_ft'],
                        'size': ol['size'],
                        'desc': ol['desc']
                    })
            else:
                has_stick = True
                stick_items = []
                cr = framing['common_rafters']
                if cr['count'] > 0:
                    stick_items.append({
                        'category': 'common_rafters',
                        'section_name': sec.name,
                        'count': cr['count'],
                        'stock_len_ft': cr['stock_len_ft'],
                        'size': cr['size'],
                        'is_engineered': cr['is_engineered'],
                        'desc': cr['desc']
                    })
                hr = framing.get('hip_rafters')
                if hr and hr['count'] > 0:
                    stick_items.append({
                        'category': 'hip_rafters',
                        'section_name': sec.name,
                        'count': hr['count'],
                        'stock_len_ft': hr['stock_len_ft'],
                        'size': hr['size'],
                        'is_engineered': hr['is_engineered'],
                        'desc': hr['desc']
                    })
                vr = framing.get('valley_rafters')
                if vr and vr['count'] > 0:
                    stick_items.append({
                        'category': 'valley_rafters',
                        'section_name': sec.name,
                        'count': vr['count'],
                        'stock_len_ft': vr['stock_len_ft'],
                        'size': vr['size'],
                        'is_engineered': vr['is_engineered'],
                        'desc': vr['desc']
                    })
                jr = framing.get('jack_rafters')
                if jr and jr['count'] > 0:
                    stick_items.append({
                        'category': 'jack_rafters',
                        'section_name': sec.name,
                        'count': jr['count'],
                        'stock_len_ft': jr['stock_len_ft'],
                        'size': jr['size'],
                        'is_engineered': jr['is_engineered'],
                        'desc': jr['desc']
                    })
                fl = framing.get('fly_rafters')
                if fl and fl['count'] > 0:
                    stick_items.append({
                        'category': 'fly_rafters',
                        'section_name': sec.name,
                        'count': fl['count'],
                        'stock_len_ft': fl['stock_len_ft'],
                        'size': fl['size'],
                        'is_engineered': fl['is_engineered'],
                        'desc': fl['desc']
                    })
                ol = framing.get('outlookers')
                if ol and ol['count'] > 0:
                    stick_items.append({
                        'category': 'outlookers',
                        'section_name': sec.name,
                        'count': ol['boards_16ft'],
                        'stock_len_ft': 16.0,
                        'size': ol['size'],
                        'is_engineered': False,
                        'desc': ol['desc']
                    })
                bb = framing.get('bird_blocking')
                if bb and bb['count'] > 0:
                    stick_items.append({
                        'category': 'bird_blocking',
                        'section_name': sec.name,
                        'count': bb['count'],
                        'stock_len_ft': 16.0,
                        'size': bb['size'],
                        'is_engineered': False,
                        'desc': bb['desc']
                    })
                rb = framing['ridge_beam']
                if rb['count'] > 0:
                    stick_items.append({
                        'category': 'ridge_beam',
                        'section_name': sec.name,
                        'count': rb['count'],
                        'stock_len_ft': 16.0,
                        'size': rb['size'],
                        'is_lvl': rb['is_lvl'],
                        'desc': rb['desc']
                    })
                rafter_details.extend(stick_items)
                collar_ties_12ft += framing['collar_ties_12ft']

            section_summaries.append({
                'name': sec.name,
                'type': sec.roof_type,
                'framing_type': sec.framing_type_display,
                'pitch': f"{sec.pitch_rise}:12",
                'sketched_overhang_in': sec.sketched_overhang_in,
                'snapped_overhang_in': sec.snapped_overhang_in,
                'area_sqft': area,
                'net_squares': area / SQFT_PER_SQUARE,
                'lines': lines,
                'framing': framing
            })

        waste_factor = 1.0 + (self.waste_percent / 100.0)
        total_gross_area_sqft = total_net_area_sqft * waste_factor
        total_squares_needed = math.ceil(total_gross_area_sqft / SQFT_PER_SQUARE)
        shingle_bundles_needed = total_squares_needed * BUNDLES_PER_SQUARE

        synthetic_underlayment_rolls = math.ceil(total_gross_area_sqft / SYNTHETIC_UNDERLAYMENT_SQFT_PER_ROLL)
        ice_water_sqft = (total_eave_lf * 3.0) + (total_valley_lf * 3.0)
        ice_water_rolls = math.ceil(ice_water_sqft / ICE_WATER_SHIELD_SQFT_PER_ROLL)

        total_drip_edge_lf = total_eave_lf + total_rake_lf
        drip_edge_sticks = math.ceil(total_drip_edge_lf / DRIP_EDGE_STICK_LEN_FT)

        total_hip_ridge_cap_lf = total_ridge_lf + total_hip_lf
        ridge_cap_bundles = math.ceil(total_hip_ridge_cap_lf / RIDGE_CAP_COVERAGE_LF_PER_BUNDLE)

        if total_valley_lf > 0:
            step_flashing_pcs = math.ceil((total_valley_lf * 12.0) / 5.6) + 2
            step_flashing_packs = math.ceil(step_flashing_pcs / float(STEP_FLASHING_PCS_PER_PACK))
        else:
            step_flashing_pcs = 0
            step_flashing_packs = 0

        total_fascia_lf = total_eave_lf + total_rake_lf
        fascia_16ft_boards = math.ceil(total_fascia_lf / FASCIA_BOARD_STOCK_LEN_FT)

        sheet_sqft = self.sheathing_sheet_width_ft * self.sheathing_sheet_height_ft
        total_sheathing_sheets = math.ceil(total_gross_area_sqft / sheet_sqft)

        framing_summary = {
            'has_truss': has_truss,
            'has_stick': has_stick,
            'total_trusses': total_trusses,
            'common_trusses': common_trusses,
            'gable_end_trusses': gable_end_trusses,
            'hip_truss_sets': hip_truss_sets,
            'truss_bracing_16ft': truss_bracing_16ft,
            'truss_fly_rafters': truss_fly_rafters,
            'truss_outlookers': truss_outlookers,
            'truss_bird_blocking_16ft': truss_bird_blocking_16ft,
            'rafter_details': rafter_details,
            'collar_ties_12ft': collar_ties_12ft
        }

        return {
            'project_name': self.project_name,
            'section_summaries': section_summaries,
            'total_net_area_sqft': total_net_area_sqft,
            'total_gross_area_sqft': total_gross_area_sqft,
            'waste_percent': self.waste_percent,
            'sheathing_thickness': self.sheathing_thickness,
            'sheathing_type': self.sheathing_type,
            'total_sheathing_sheets': total_sheathing_sheets,
            'total_squares_needed': total_squares_needed,
            'shingle_bundles_needed': shingle_bundles_needed,
            'synthetic_underlayment_rolls': synthetic_underlayment_rolls,
            'ice_water_sqft': ice_water_sqft,
            'ice_water_rolls': ice_water_rolls,
            'total_eave_lf': total_eave_lf,
            'total_ridge_lf': total_ridge_lf,
            'total_hip_lf': total_hip_lf,
            'total_valley_lf': total_valley_lf,
            'total_rake_lf': total_rake_lf,
            'total_drip_edge_lf': total_drip_edge_lf,
            'drip_edge_sticks': drip_edge_sticks,
            'total_hip_ridge_cap_lf': total_hip_ridge_cap_lf,
            'ridge_cap_bundles': ridge_cap_bundles,
            'step_flashing_pcs': step_flashing_pcs,
            'step_flashing_packs': step_flashing_packs,
            'total_fascia_lf': total_fascia_lf,
            'fascia_16ft_boards': fascia_16ft_boards,
            'framing_summary': framing_summary
        }


def format_takeoff_report(results: Dict) -> str:
    lines = []
    lines.append("=" * 80)
    lines.append(f" ROOF MATERIAL TAKEOFF REPORT: {results['project_name']}")
    lines.append("=" * 80)

    lines.append("\nSECTION BREAKDOWN & INFERRED OVERHANGS:")
    lines.append("-" * 80)
    for s in results['section_summaries']:
        lines.append(f"• {s['name']} ({s['type'].upper()} Roof - Pitch {s['pitch']} | Framing: {s['framing_type']}):")
        lines.append(f"    - Sketched Overhang: {s['sketched_overhang_in']:.1f}\" -> Snapped Standard Overhang: {s['snapped_overhang_in']:.0f}\"")
        lines.append(f"    - 3D Sloped Surface Area: {s['area_sqft']:.1f} sq ft ({s['net_squares']:.2f} Squares)")
        l = s['lines']
        lines.append(f"    - Linear Elements: Eaves={l['eave_lf']:.1f}' | Ridge={l['ridge_lf']:.1f}' | Hips={l['hip_lf']:.1f}' | Valleys={l['valley_lf']:.1f}' | Rakes={l['rake_lf']:.1f}'")
        lines.append("-" * 80)

    lines.append("\nCOMBINED MATERIAL PURCHASE LIST:")
    lines.append("=" * 80)
    lines.append(f"1. ROOFING SHINGLES (Architectural / 3-Tab):")
    lines.append(f"   • Net Roof Area:       {results['total_net_area_sqft']:.1f} sq ft ({results['total_net_area_sqft']/100.0:.2f} Squares)")
    lines.append(f"   • Gross Area (+{results['waste_percent']:.0f}% Waste): {results['total_gross_area_sqft']:.1f} sq ft")
    lines.append(f"   • TOTAL SQUARES TO ORDER:  {results['total_squares_needed']} Squares")
    lines.append(f"   • SHINGLE BUNDLES TO ORDER: {results['shingle_bundles_needed']} Bundles (3 bundles/square)")

    lines.append(f"\n2. UNDERLAYMENT & MOISTURE BARRIERS:")
    lines.append(f"   • Synthetic Underlayment:   {results['synthetic_underlayment_rolls']} Roll(s) (1,000 sq ft/roll)")
    lines.append(f"   • Ice & Water Shield:       {results['ice_water_rolls']} Roll(s) ({results['ice_water_sqft']:.1f} sq ft needed for eaves & valleys)")

    lines.append(f"\n3. FLASHING & EDGE ACCESSORIES:")
    lines.append(f"   • Drip Edge Metal (Eaves & Rakes): {results['total_drip_edge_lf']:.1f} LF -> {results['drip_edge_sticks']} Sticks (10' lengths)")
    lines.append(f"   • Ridge & Hip Cap Shingles:       {results['total_hip_ridge_cap_lf']:.1f} LF -> {results['ridge_cap_bundles']} Bundle(s) (35 LF/bundle)")
    if results['total_valley_lf'] > 0:
        lines.append(f"   • Metal Step Flashing Cards (4\"x4\"x8\"): {results['total_valley_lf']:.1f} LF -> {results['step_flashing_pcs']} Pcs ({results['step_flashing_packs']} Pack(s) of 50)")
    else:
        lines.append(f"   • Metal Step Flashing Cards (4\"x4\"x8\"): None required")

    lines.append(f"\n4. FASCIA LUMBER:")
    lines.append(f"   • Sub-Fascia / Trim Boards:        {results['total_fascia_lf']:.1f} LF -> {results['fascia_16ft_boards']} Board(s) (2x6 x 16' stock)")

    sheath_thick = results.get('sheathing_thickness', '5/8"')
    sheath_type = results.get('sheathing_type', 'OSB')
    sheath_sheets = results.get('total_sheathing_sheets', 0)
    lines.append(f"\n5. ROOF DECKING & SHEATHING:")
    lines.append(f"   • Roof Sheathing Decking:          {sheath_sheets} Sheet(s) (4'x8' x {sheath_thick} {sheath_type} Decking)")

    return "\n".join(lines)
