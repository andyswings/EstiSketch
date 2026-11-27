"""Builders converting ParsedProject, XML, or Canvas state into SceneIR v1."""

from __future__ import annotations

import copy
import math
from typing import Protocol, TypeVar

from .parsed import (
    INCH_TO_M,
    ParsedLevel,
    ParsedProject,
    ParsedWall,
    Point2D,
    parse_estisketch_canvas,
    parse_estisketch_xml,
)
from .schema import (
    FooterIR,
    GableInfillIR,
    LevelIR,
    OpeningCutIR,
    OpeningIR,
    RimBandIR,
    RoofFacetIR,
    RoofIR,
    RoomIR,
    SCENE_IR_SCHEMA_VERSION,
    SceneDeltaIR,
    SceneIR,
    StairIR,
    SunIR,
    WallIR,
    WallSegmentIR,
    FixtureIR,
)
from .solvers import (
    StripSegment,
    compute_centered_fixture_transform,
    compute_hb5_stair_transform,
    compute_level_wall_miters,
    compute_mitered_strip_polygons,
    compute_opening_local_x,
    compute_plan_center,
    compute_room_hole_cutouts,
    compute_stair_railing_paths_3d,
    compute_window_sill_height_m,
    inches_to_blender_xy,
    orient_interior_wall_chains,
    resolve_curved_wall_segment,
    resolve_opening_chain_placement,
    solve_roof_3d,
    tessellate_curved_wall_points,
)


class _HasId(Protocol):
    """Structural protocol for SceneIR entities keyed by ``id``."""

    id: str


_EntityT = TypeVar("_EntityT", bound=_HasId)


def _diff_entity_list(
    prev_items: list[_EntityT],
    curr_items: list[_EntityT],
    removed_ids: list[str],
) -> list[_EntityT]:
    """Return added or modified items and append deleted IDs to ``removed_ids``."""
    prev_by_id = {item.id: item for item in prev_items}
    curr_by_id = {item.id: item for item in curr_items}

    changed: list[_EntityT] = []
    for item in curr_items:
        old = prev_by_id.get(item.id)
        if old is None or old != item:
            changed.append(item)

    for old_id in prev_by_id:
        if old_id not in curr_by_id:
            removed_ids.append(old_id)

    return changed


def _seg_id(base_id: str, seg_idx: int, total_segs: int) -> str:
    """Return stable unique identifier for strip polygons belonging to a wall."""
    if total_segs <= 1:
        return base_id
    return f"{base_id}__seg_{seg_idx}"


def build_scene_ir(project: ParsedProject) -> SceneIR:
    """Build a complete centered-meter :class:`SceneIR` v1 from a ``ParsedProject``.

    Operates on a deep copy of ``project`` so ``orient_interior_wall_chains``
    does not mutate the caller's parsed project data.

    Args:
        project: Pure-Python parsed project whose dimensions are in inches.

    Returns:
        A complete :class:`SceneIR` instance (schema version 1) in meters.
    """
    work = copy.deepcopy(project)
    if not work.levels:
        work.levels.append(ParsedLevel(id="level_0", name="Level 1", elevation=0.0, height=96.0))

    orient_interior_wall_chains(work)
    cx, cy = compute_plan_center(work)

    level_by_id = {lvl.id: lvl for lvl in work.levels}
    default_level = work.levels[0]

    levels_ir = [
        LevelIR(
            id=lvl.id,
            name=lvl.name,
            elevation_m=lvl.elevation * INCH_TO_M,
            height_m=lvl.height * INCH_TO_M,
            floor_thickness_m=lvl.floor_thickness * INCH_TO_M,
        )
        for lvl in work.levels
    ]

    sun_ir = SunIR(
        north_angle_deg=work.north_angle,
        azimuth_deg=(145.0 - work.north_angle) % 360.0,
        elevation_deg=48.0,
    )

    # Precompute per-level wall miter angles for straight non-symbolic walls.
    straight_wall_entries_by_level: dict[
        str, list[tuple[str, Point2D, Point2D, float, bool]]
    ] = {}
    for pw in work.walls:
        if pw.symbolic or pw.is_curved:
            continue
        p0_m = inches_to_blender_xy(pw.start[0], pw.start[1], cx, cy)
        p1_m = inches_to_blender_xy(pw.end[0], pw.end[1], cx, cy)
        thick_m = max(0.02, pw.width * INCH_TO_M)
        straight_wall_entries_by_level.setdefault(pw.level_id, []).append(
            (pw.identifier, p0_m, p1_m, thick_m, pw.exterior_wall)
        )

    wall_miters: dict[str, tuple[float, float]] = {}
    for entries in straight_wall_entries_by_level.values():
        wall_miters.update(compute_level_wall_miters(entries))

    # Build WallIR entries (non-symbolic walls) and lookup indices for openings.
    wall_ir_list: list[WallIR] = []
    wall_by_ref: dict[tuple[int, int], ParsedWall] = {}
    wall_ir_by_id: dict[str, WallIR] = {}
    seg_lengths_by_wall_id: dict[str, list[float]] = {}

    for pw in work.walls:
        if pw.symbolic:
            continue
        wall_by_ref[(pw.set_index, pw.wall_index)] = pw

        if pw.is_curved and pw.arc_center is not None and pw.arc_radius is not None:
            pts_in = tessellate_curved_wall_points(
                pw.start, pw.end, pw.arc_center, pw.arc_radius
            )
        else:
            pts_in = [pw.start, pw.end]
        pts_m = [inches_to_blender_xy(x, y, cx, cy) for x, y in pts_in]

        thick_m = max(0.02, pw.width * INCH_TO_M)
        h0_m = pw.height * INCH_TO_M
        h1_m = pw.height_at_end * INCH_TO_M
        num_segs = max(1, len(pts_m) - 1)
        miter_l, miter_r = wall_miters.get(pw.identifier, (0.0, 0.0))

        seg_irs: list[WallSegmentIR] = []
        seg_lens: list[float] = []
        for idx in range(len(pts_m) - 1):
            p0 = pts_m[idx]
            p1 = pts_m[idx + 1]
            seg_len = math.hypot(p1[0] - p0[0], p1[1] - p0[1])
            seg_lens.append(seg_len)
            t0 = idx / num_segs
            t1 = (idx + 1) / num_segs
            sh0 = h0_m + (h1_m - h0_m) * t0
            sh1 = h0_m + (h1_m - h0_m) * t1
            seg_irs.append(
                WallSegmentIR(
                    seg_index=idx,
                    start_m=p0,
                    end_m=p1,
                    thickness_m=thick_m,
                    height_start_m=sh0,
                    height_end_m=sh1,
                    left_angle_rad=miter_l if idx == 0 else 0.0,
                    right_angle_rad=miter_r if idx == num_segs - 1 else 0.0,
                    exterior=pw.exterior_wall,
                    left_finish=pw.left_finish,
                    right_finish=pw.right_finish,
                    left_color=pw.left_color,
                    right_color=pw.right_color,
                    left_baseboard=pw.left_baseboard,
                    right_baseboard=pw.right_baseboard,
                    opening_cuts=[],
                )
            )

        wall_ir = WallIR(
            id=pw.identifier,
            level_id=pw.level_id,
            layer_id=pw.layer_id,
            visible=True,
            locked=False,
            segments=seg_irs,
            custom_3d_override=None,
        )
        wall_ir_list.append(wall_ir)
        wall_ir_by_id[pw.identifier] = wall_ir
        seg_lengths_by_wall_id[pw.identifier] = seg_lens

    non_symbolic_walls = [w for w in work.walls if not w.symbolic]
    openings_ir: list[OpeningIR] = []

    def _register_opening(
        op_id: str,
        kind: str,
        host_pw: ParsedWall,
        ratio: float,
        op_width_in: float,
        op_height_in: float,
        style: str,
        swing: str,
        orientation: str,
    ) -> None:
        host_wir = wall_ir_by_id.get(host_pw.identifier)
        seg_lens = seg_lengths_by_wall_id.get(host_pw.identifier, [])
        if host_wir is None or not host_wir.segments:
            return

        depth_m = max(0.05, host_pw.width * INCH_TO_M)
        if not host_pw.is_curved:
            placement = resolve_opening_chain_placement(
                host_pw, ratio, op_width_in, non_symbolic_walls
            )
            wall_len_m = seg_lens[0] if seg_lens else 0.0
            x_local_m = (
                placement.x_local_m
                if placement.cuts
                else compute_opening_local_x(ratio, wall_len_m, placement.width_m)
            )
            host_seg_index = 0
            host_min_h = placement.min_height_m
            width_m = placement.width_m
            height_m = max(0.2, min(op_height_in * INCH_TO_M, host_min_h - 0.03))
            z_local_m = (
                0.0
                if kind == "door"
                else compute_window_sill_height_m(height_m, host_min_h)
            )
            z0_cut = z_local_m
            z1_cut = z_local_m + height_m

            for cut in placement.cuts:
                cut_wir = wall_ir_by_id.get(cut.wall.identifier)
                if cut_wir and cut_wir.segments:
                    cut_wir.segments[0].opening_cuts.append(
                        OpeningCutIR(
                            opening_id=op_id,
                            x0_m=cut.x_start_m,
                            x1_m=cut.x_end_m,
                            z0_m=z0_cut,
                            z1_m=z1_cut,
                        )
                    )
        else:
            host_seg_index, local_ratio = resolve_curved_wall_segment(seg_lens, ratio)
            seg_ir = host_wir.segments[host_seg_index]
            seg_len_m = seg_lens[host_seg_index]
            width_m = max(0.1, min(op_width_in * INCH_TO_M, seg_len_m))
            x_local_m = compute_opening_local_x(local_ratio, seg_len_m, width_m)
            host_min_h = min(seg_ir.height_start_m, seg_ir.height_end_m)
            height_m = max(0.2, min(op_height_in * INCH_TO_M, host_min_h - 0.03))
            z_local_m = (
                0.0
                if kind == "door"
                else compute_window_sill_height_m(height_m, host_min_h)
            )
            seg_ir.opening_cuts.append(
                OpeningCutIR(
                    opening_id=op_id,
                    x0_m=x_local_m,
                    x1_m=x_local_m + width_m,
                    z0_m=z_local_m,
                    z1_m=z_local_m + height_m,
                )
            )

        openings_ir.append(
            OpeningIR(
                id=op_id,
                kind=kind,
                host_wall_id=host_pw.identifier,
                host_seg_index=host_seg_index,
                x_local_m=x_local_m,
                z_local_m=z_local_m,
                width_m=width_m,
                depth_m=depth_m,
                height_m=height_m,
                style=style,
                swing=swing,
                orientation=orientation,
            )
        )

    for pd in work.doors:
        host_pw = wall_by_ref.get((pd.set_index, pd.wall_index))
        if host_pw is not None:
            _register_opening(
                op_id=pd.identifier,
                kind="door",
                host_pw=host_pw,
                ratio=pd.ratio,
                op_width_in=pd.width,
                op_height_in=pd.height,
                style=pd.door_type,
                swing=pd.swing,
                orientation=pd.orientation,
            )

    for pw_win in work.windows:
        host_pw = wall_by_ref.get((pw_win.set_index, pw_win.wall_index))
        if host_pw is not None:
            _register_opening(
                op_id=pw_win.identifier,
                kind="window",
                host_pw=host_pw,
                ratio=pw_win.ratio,
                op_width_in=pw_win.width,
                op_height_in=pw_win.height,
                style=pw_win.window_type,
                swing="",
                orientation="",
            )

    # Rooms & cutouts
    cutouts_by_room = compute_room_hole_cutouts(work)
    rooms_ir: list[RoomIR] = []
    for room in work.rooms:
        lvl = level_by_id.get(room.level_id, default_level)
        outer_m = [inches_to_blender_xy(x, y, cx, cy) for x, y in room.points]
        room_cuts = cutouts_by_room.get(room.identifier, [])
        floor_holes_m = [
            [inches_to_blender_xy(x, y, cx, cy) for x, y in cut.points]
            for cut in room_cuts
            if cut.cuts_floor
        ]
        ceiling_holes_m = [
            [inches_to_blender_xy(x, y, cx, cy) for x, y in cut.points]
            for cut in room_cuts
            if cut.cuts_ceiling
        ]
        thick_in = room.slab_thickness if room.is_slab else lvl.floor_thickness
        rooms_ir.append(
            RoomIR(
                id=room.identifier,
                level_id=room.level_id,
                name=room.name,
                outer_m=outer_m,
                floor_holes_m=floor_holes_m,
                ceiling_holes_m=ceiling_holes_m,
                z_top_m=lvl.elevation * INCH_TO_M,
                thickness_m=max(0.02, thick_in * INCH_TO_M),
                ceiling_z_m=(lvl.elevation + room.height) * INCH_TO_M,
                floor_pattern=room.floor_pattern,
                pattern_rotation_deg=room.pattern_rotation,
                pattern_scale=room.pattern_scale,
            )
        )

    # Roofs
    ext_siding = ""
    for pw in non_symbolic_walls:
        if pw.exterior_wall and pw.exterior_finish:
            ext_siding = pw.exterior_finish
            break
    roofs_ir: list[RoofIR] = []
    for roof in work.roofs:
        solved = solve_roof_3d(roof, work)
        facets_ir: list[RoofFacetIR] = []
        for facet in solved.facets:
            verts_m = []
            for x_in, y_in, z_in in facet.vertices_3d:
                xm, ym = inches_to_blender_xy(x_in, y_in, cx, cy)
                verts_m.append((xm, ym, z_in * INCH_TO_M))
            facets_ir.append(RoofFacetIR(vertices_m=verts_m, pitch_rise=facet.pitch_rise))

        infills_ir: list[GableInfillIR] = []
        for infill in solved.gable_infills:
            infills_ir.append(
                GableInfillIR(
                    p_start_m=inches_to_blender_xy(
                        infill.p_start[0], infill.p_start[1], cx, cy
                    ),
                    p_end_m=inches_to_blender_xy(infill.p_end[0], infill.p_end[1], cx, cy),
                    p_peak_m=inches_to_blender_xy(infill.p_peak[0], infill.p_peak[1], cx, cy),
                    z_base_m=infill.z_base * INCH_TO_M,
                    z_peak_m=infill.z_peak * INCH_TO_M,
                    thickness_m=max(0.02, infill.thickness * INCH_TO_M),
                    finish=ext_siding or "Drywall",
                )
            )
        roofs_ir.append(
            RoofIR(
                id=solved.roof_id,
                level_id=solved.level_id,
                material=solved.material,
                thickness_m=8.0 * INCH_TO_M,
                facets=facets_ir,
                gable_infills=infills_ir,
            )
        )

    # Footers
    footer_groups: dict[tuple[str, float], list[ParsedWall]] = {}
    for pw in work.walls:
        if pw.footer:
            footer_groups.setdefault((pw.level_id, round(pw.footer_depth, 3)), []).append(pw)

    footers_ir: list[FooterIR] = []
    for (lvl_id, _), group_walls in footer_groups.items():
        lvl = level_by_id.get(lvl_id, default_level)
        segs: list[StripSegment] = []
        seg_ranges: list[tuple[ParsedWall, int, int]] = []
        for pw in group_walls:
            if pw.is_curved and pw.arc_center is not None and pw.arc_radius is not None:
                pts_in = tessellate_curved_wall_points(
                    pw.start, pw.end, pw.arc_center, pw.arc_radius
                )
            else:
                pts_in = [pw.start, pw.end]
            pts_m = [inches_to_blender_xy(x, y, cx, cy) for x, y in pts_in]
            thick_m = max(0.02, pw.width * INCH_TO_M)
            left_off_m = max(0.0, pw.footer_left_offset * INCH_TO_M)
            right_off_m = max(0.0, pw.footer_right_offset * INCH_TO_M)
            if pw.symbolic:
                y0 = -(thick_m / 2.0 + left_off_m)
                y1 = thick_m / 2.0 + right_off_m
            else:
                y0 = -left_off_m
                y1 = thick_m + right_off_m
            start_idx = len(segs)
            for idx in range(len(pts_m) - 1):
                segs.append(StripSegment(pts_m[idx], pts_m[idx + 1], y0, y1))
            seg_ranges.append((pw, start_idx, len(segs)))

        polys = compute_mitered_strip_polygons(segs)
        for pw, s_idx, e_idx in seg_ranges:
            seg_polys = [poly for poly in polys[s_idx:e_idx] if len(poly) >= 3]
            for p_idx, poly in enumerate(seg_polys):
                footers_ir.append(
                    FooterIR(
                        id=_seg_id(f"footer:{pw.identifier}", p_idx, len(seg_polys)),
                        level_id=lvl.id,
                        footprint_m=poly,
                        z_top_m=lvl.elevation * INCH_TO_M,
                        depth_m=max(0.05, pw.footer_depth * INCH_TO_M),
                    )
                )

    # Rim bands for upper levels
    rim_bands_ir: list[RimBandIR] = []
    for lvl in work.levels:
        if lvl.elevation <= 0.1 or lvl.floor_thickness <= 0.01:
            continue
        ext_walls = [
            pw
            for pw in non_symbolic_walls
            if pw.level_id == lvl.id and pw.exterior_wall
        ]
        if not ext_walls:
            continue
        z_bot_m = (lvl.elevation - lvl.floor_thickness) * INCH_TO_M
        height_m = lvl.floor_thickness * INCH_TO_M
        segs = []
        seg_ranges = []
        for pw in ext_walls:
            if pw.is_curved and pw.arc_center is not None and pw.arc_radius is not None:
                pts_in = tessellate_curved_wall_points(
                    pw.start, pw.end, pw.arc_center, pw.arc_radius
                )
            else:
                pts_in = [pw.start, pw.end]
            pts_m = [inches_to_blender_xy(x, y, cx, cy) for x, y in pts_in]
            thick_m = max(0.02, pw.width * INCH_TO_M)
            start_idx = len(segs)
            for idx in range(len(pts_m) - 1):
                segs.append(StripSegment(pts_m[idx], pts_m[idx + 1], 0.0, thick_m))
            seg_ranges.append((pw, start_idx, len(segs)))

        polys = compute_mitered_strip_polygons(segs)
        for pw, s_idx, e_idx in seg_ranges:
            seg_polys = [poly for poly in polys[s_idx:e_idx] if len(poly) >= 3]
            for p_idx, poly in enumerate(seg_polys):
                rim_bands_ir.append(
                    RimBandIR(
                        id=_seg_id(f"rim:{pw.identifier}", p_idx, len(seg_polys)),
                        level_id=lvl.id,
                        footprint_m=poly,
                        z_bottom_m=z_bot_m,
                        height_m=height_m,
                    )
                )

    # Stairs
    stairs_ir: list[StairIR] = []
    for stair in work.stairs:
        lvl = (
            level_by_id.get(stair.start_level_id) or level_by_id.get(stair.level_id) or default_level
        )
        loc_m, rot_z_rad = compute_hb5_stair_transform(stair, lvl.elevation, cx, cy)
        rail_paths_in = compute_stair_railing_paths_3d(stair, lvl.elevation)
        rail_paths_m = [
            [
                (*inches_to_blender_xy(px, py, cx, cy), pz * INCH_TO_M)
                for px, py, pz in path
            ]
            for path in rail_paths_in
        ]
        stairs_ir.append(
            StairIR(
                id=stair.identifier,
                level_id=lvl.id,
                stair_type=stair.stair_type,
                loc_m=loc_m,
                rot_z_rad=rot_z_rad,
                width_m=stair.width * INCH_TO_M,
                total_rise_m=stair.total_rise * INCH_TO_M,
                num_steps=stair.num_steps,
                tread_depth_m=stair.tread_depth * INCH_TO_M,
                total_run_m=stair.total_run * INCH_TO_M,
                turn_direction=stair.turn_direction,
                landing_depth_m=stair.landing_depth * INCH_TO_M,
                steps_before_landing=stair.steps_before_landing,
                winder_count=stair.winder_count,
                inner_radius_m=stair.inner_radius * INCH_TO_M,
                rotation_degrees=stair.rotation_degrees,
                has_left_rail=stair.has_left_rail,
                has_right_rail=stair.has_right_rail,
                rail_height_m=stair.rail_height * INCH_TO_M,
                railing_paths_m=rail_paths_m,
            )
        )

    # Fixtures
    fixtures_ir: list[FixtureIR] = []
    for fx in work.fixtures:
        lvl = level_by_id.get(fx.level_id, default_level)
        loc_m, rot_z_rad = compute_centered_fixture_transform(fx, lvl.elevation, cx, cy)
        fixtures_ir.append(
            FixtureIR(
                id=fx.identifier,
                level_id=lvl.id,
                symbol_type=fx.symbol_type,
                category=fx.category,
                loc_m=loc_m,
                rot_z_rad=rot_z_rad,
                width_m=fx.width * INCH_TO_M,
                depth_m=fx.depth * INCH_TO_M,
                height_m=fx.height * INCH_TO_M,
                has_countertop=fx.has_countertop,
                countertop_overhang_m=fx.countertop_overhang * INCH_TO_M,
                countertop_thickness_m=fx.countertop_thickness * INCH_TO_M,
                countertop_material=fx.countertop_material,
                has_backsplash=fx.has_backsplash,
                fill_color=fx.fill_color,
                countertop_color=fx.countertop_color,
            )
        )

    return SceneIR(
        schema_version=SCENE_IR_SCHEMA_VERSION,
        plan_center_in=(cx, cy),
        sun=sun_ir,
        levels=levels_ir,
        walls=wall_ir_list,
        openings=openings_ir,
        rooms=rooms_ir,
        roofs=roofs_ir,
        footers=footers_ir,
        rim_bands=rim_bands_ir,
        stairs=stairs_ir,
        fixtures=fixtures_ir,
        custom_assets=[],
    )


def build_scene_ir_from_xml(xml_path: str) -> SceneIR:
    """Parse an EstiSketch ``.xml`` project file and build a :class:`SceneIR`."""
    return build_scene_ir(parse_estisketch_xml(xml_path))


def build_scene_ir_from_canvas(canvas: object) -> SceneIR:
    """Extract a live EstiSketch canvas directly into a :class:`SceneIR`."""
    return build_scene_ir(parse_estisketch_canvas(canvas))


def diff_scene_ir(prev: SceneIR, curr: SceneIR) -> SceneDeltaIR:
    """Compute an incremental :class:`SceneDeltaIR` between two snapshots.

    Args:
        prev: Previous :class:`SceneIR` state already loaded in the renderer.
        curr: Newly built :class:`SceneIR` state.

    Returns:
        A :class:`SceneDeltaIR` containing only added/modified entities and
        deleted entity IDs in ``removed_ids``.
    """
    removed_ids: list[str] = []
    return SceneDeltaIR(
        schema_version=curr.schema_version,
        plan_center_in=curr.plan_center_in,
        sun=curr.sun,
        levels=_diff_entity_list(prev.levels, curr.levels, removed_ids),
        walls=_diff_entity_list(prev.walls, curr.walls, removed_ids),
        openings=_diff_entity_list(prev.openings, curr.openings, removed_ids),
        rooms=_diff_entity_list(prev.rooms, curr.rooms, removed_ids),
        roofs=_diff_entity_list(prev.roofs, curr.roofs, removed_ids),
        footers=_diff_entity_list(prev.footers, curr.footers, removed_ids),
        rim_bands=_diff_entity_list(prev.rim_bands, curr.rim_bands, removed_ids),
        stairs=_diff_entity_list(prev.stairs, curr.stairs, removed_ids),
        fixtures=_diff_entity_list(prev.fixtures, curr.fixtures, removed_ids),
        custom_assets=_diff_entity_list(prev.custom_assets, curr.custom_assets, removed_ids),
        removed_ids=sorted(set(removed_ids)),
    )
