"""Convert an EstiSketch XML project into a native Home Builder 5 Blender scene.

Usage inside Blender:
    blender --python estisketch_to_hb5.py -- <project.xml> [--save-blend <out.blend>]

The XML parsing and coordinate conversion helpers (Layer 1) live in
``EstiSketch.scene_ir`` and do not import ``bpy`` so they can be unit-tested
directly under standard Python.
"""

from __future__ import annotations

import math
import os
import sys
from typing import Dict, List, Optional, Tuple

if __package__ in (None, ""):
    _src_root = os.path.dirname(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    )
    if _src_root not in sys.path:
        sys.path.insert(0, _src_root)

from EstiSketch.scene_ir import (  # noqa: E402
    INCH_TO_M,
    OpeningChainPlacement,
    ParsedDoor,
    ParsedFixture,
    ParsedFloorOpening,
    ParsedLevel,
    ParsedProject,
    ParsedRoof,
    ParsedRoofEdge,
    ParsedRoom,
    ParsedStair,
    ParsedWall,
    ParsedWindow,
    RoomHoleCutout,
    SolvedGableInfill,
    SolvedRoofFacet,
    SolvedRoofGeometry,
    StripSegment,
    WallOpeningCut,
    _l_stair_layout_in,
    _winder_tread_polys_local,
    collinear_parsed_wall_chain,
    compute_baseboard_spans,
    compute_centered_fixture_transform,
    compute_hb5_fixture_transform,
    compute_hb5_stair_transform,
    compute_level_wall_miters,
    compute_mitered_strip_polygons,
    compute_opening_local_x,
    compute_plan_center,
    compute_room_hole_cutouts,
    compute_stair_footprint_parts,
    compute_stair_railing_paths_3d,
    compute_sun_rotation_euler,
    compute_window_sill_height_m,
    inches_to_blender_xy,
    orient_interior_wall_chains,
    parse_estisketch_xml,
    resolve_curved_wall_segment,
    resolve_opening_chain_placement,
    solve_hb5_miter_angles,
    solve_roof_3d,
    tessellate_curved_wall_points,
)


# ---------------------------------------------------------------------------
# Layer 2: Blender + Home Builder 5 scene builder (lazy bpy import)
# ---------------------------------------------------------------------------


def find_hb5_package() -> str:
    """Return the enabled ``home_builder_5`` addon module name in Blender."""
    import bpy

    for key in bpy.context.preferences.addons.keys():
        if key == "home_builder_5" or key.endswith(".home_builder_5"):
            return key
    raise RuntimeError(
        "Home Builder 5 extension is not enabled in Blender. "
        "Enable 'Home Builder 5' in Edit > Preferences > Get Extensions / Add-ons."
    )


def _ensure_collection(name: str, parent) -> object:
    import bpy

    col = bpy.data.collections.get(name)
    if col is None:
        col = bpy.data.collections.new(name)
        parent.children.link(col)
    elif col.name not in [c.name for c in parent.children]:
        parent.children.link(col)
    return col


def _move_object_to_collection(obj, target_col) -> None:
    if target_col not in obj.users_collection:
        target_col.objects.link(obj)
    for col in list(obj.users_collection):
        if col != target_col:
            col.objects.unlink(obj)


def _clear_default_scene(scene) -> None:
    import bpy

    for obj in list(scene.objects):
        bpy.data.objects.remove(obj, do_unlink=True)


def _ensure_sun_light(scene, target_col, north_angle: float = 0.0) -> None:
    import bpy

    light_data = bpy.data.lights.new(name="EstiSketch Sun", type="SUN")
    light_data.energy = 2.5
    light_obj = bpy.data.objects.new(name="EstiSketch Sun", object_data=light_data)
    light_obj.rotation_euler = compute_sun_rotation_euler(north_angle)
    target_col.objects.link(light_obj)


_WALL_FINISH_PRESETS: Dict[str, Tuple[str, Tuple[float, float, float], Optional[Tuple[float, float, float]], float, dict]] = {
    "drywall": ("SOLID", (0.91, 0.90, 0.87), None, 0.72, {}),
    "painted drywall": ("SOLID", (0.91, 0.90, 0.87), None, 0.65, {}),
    "plaster": ("SOLID", (0.90, 0.87, 0.82), None, 0.78, {}),
    "tile": ("TILE", (0.92, 0.92, 0.91), (0.65, 0.65, 0.64), 0.18, {"tile_w": 6 * INCH_TO_M, "tile_h": 3 * INCH_TO_M, "running_bond": True}),
    "t&g wood": ("WOOD", (0.60, 0.43, 0.27), (0.45, 0.30, 0.17), 0.45, {"tile_h": 5 * INCH_TO_M}),
    "wainscoting": ("WOOD", (0.88, 0.87, 0.84), (0.76, 0.75, 0.72), 0.42, {"tile_h": 4 * INCH_TO_M}),
    "vinyl siding": ("TILE", (0.76, 0.79, 0.81), (0.58, 0.61, 0.64), 0.52, {"tile_w": 2.4, "tile_h": 7 * INCH_TO_M, "running_bond": False, "grout_size": 0.006}),
    "hardie lap siding": ("TILE", (0.62, 0.66, 0.64), (0.44, 0.48, 0.46), 0.62, {"tile_w": 2.4, "tile_h": 7 * INCH_TO_M, "running_bond": False, "grout_size": 0.007}),
    "stucco": ("SOLID", (0.84, 0.79, 0.70), None, 0.88, {}),
    "brick": ("TILE", (0.55, 0.24, 0.17), (0.72, 0.70, 0.66), 0.82, {"tile_w": 8 * INCH_TO_M, "tile_h": 2.67 * INCH_TO_M, "running_bond": True, "grout_size": 0.010}),
    "stone veneer": ("STONE", (0.54, 0.52, 0.48), (0.36, 0.34, 0.32), 0.82, {}),
    "exposed concrete": ("SOLID", (0.56, 0.56, 0.55), None, 0.85, {}),
    "none": ("SOLID", (0.68, 0.58, 0.42), None, 0.80, {}),
}


def _resolve_wall_side_finishes(pw: ParsedWall) -> Tuple[str, str]:
    lf = pw.left_finish or "Drywall"
    rf = pw.right_finish or "Drywall"
    if (
        pw.exterior_wall
        and lf.lower() == "drywall"
        and rf.lower() == "drywall"
        and pw.exterior_finish
        and "drywall" not in pw.exterior_finish.lower()
    ):
        rf = pw.exterior_finish
    return (lf, rf)


def _get_or_create_wall_finish_material(
    finish_name: str,
    color_rgb: Optional[Tuple[float, float, float]],
    surface_materials,
    fallback_mat=None,
):
    import bpy

    key = (finish_name or "drywall").strip().lower()
    preset = _WALL_FINISH_PRESETS.get(key)
    if preset is None:
        if "siding" in key:
            preset = _WALL_FINISH_PRESETS["hardie lap siding"]
        elif "stucco" in key:
            preset = _WALL_FINISH_PRESETS["stucco"]
        elif "brick" in key:
            preset = _WALL_FINISH_PRESETS["brick"]
        elif "stone" in key:
            preset = _WALL_FINISH_PRESETS["stone veneer"]
        elif "tile" in key:
            preset = _WALL_FINISH_PRESETS["tile"]
        elif "wood" in key:
            preset = _WALL_FINISH_PRESETS["t&g wood"]
        elif "concrete" in key:
            preset = _WALL_FINISH_PRESETS["exposed concrete"]
        elif color_rgb is None and fallback_mat is not None:
            return fallback_mat
        else:
            preset = _WALL_FINISH_PRESETS["drywall"]

    style, base_srgb, accent_srgb, rough, extra = preset
    if color_rgb is not None:
        base_srgb = color_rgb
        if accent_srgb is not None:
            accent_srgb = tuple(max(0.0, c * 0.72) for c in color_rgb)
        hex_tag = "".join(f"{round(max(0.0, min(1.0, c)) * 255):02x}" for c in color_rgb)
    else:
        hex_tag = "default"

    slug = "".join(ch if ch.isalnum() else "_" for ch in key).strip("_") or "drywall"
    mat_id = f"EstiSketch_Wall_{slug}_{hex_tag}"
    existing = bpy.data.materials.get(mat_id)
    if existing is not None:
        return existing

    mat = surface_materials.build_surface_material(
        mat_id, style, base_srgb, accent_srgb, rough, **extra
    )
    mat.diffuse_color = (*base_srgb, 1.0)
    return mat


def _assign_wall_materials(
    wall, scene, pw: Optional[ParsedWall] = None, surface_materials=None
) -> None:
    fallback = getattr(scene.home_builder, "wall_material", None)
    if pw is not None and surface_materials is not None:
        lf, rf = _resolve_wall_side_finishes(pw)
        left_mat = _get_or_create_wall_finish_material(
            lf, pw.left_color, surface_materials, fallback
        )
        right_mat = _get_or_create_wall_finish_material(
            rf, pw.right_color, surface_materials, fallback
        )
        edge_mat = right_mat if pw.exterior_wall else left_mat
    else:
        left_mat = right_mat = edge_mat = fallback

    if left_mat is not None and wall.has_input("Left Edge"):
        wall.set_input("Left Edge", left_mat)
    if right_mat is not None and wall.has_input("Right Edge"):
        wall.set_input("Right Edge", right_mat)

    if edge_mat is not None:
        for slot in (
            "Top Surface",
            "Bottom Surface",
            "Inside Face",
            "Outside Face",
            "Left Surface",
            "Right Surface",
            "Front Surface",
            "Back Surface",
        ):
            if wall.has_input(slot):
                wall.set_input(slot, edge_mat)


_FLOOR_PATTERN_PRESETS: Dict[str, Tuple[str, Tuple[float, float, float], Optional[Tuple[float, float, float]], float, dict]] = {
    "wood_plank": ("WOOD", (0.58, 0.42, 0.27), (0.42, 0.28, 0.16), 0.38, {"tile_h": 0.14}),
    "herringbone": ("WOOD", (0.55, 0.39, 0.24), (0.39, 0.26, 0.15), 0.36, {"tile_h": 0.10}),
    "chevron": ("WOOD", (0.60, 0.44, 0.28), (0.44, 0.30, 0.17), 0.36, {"tile_h": 0.11}),
    "vinyl_plank": ("WOOD", (0.65, 0.56, 0.44), (0.50, 0.42, 0.32), 0.35, {"tile_h": 0.18}),
    "tile_12": ("TILE", (0.84, 0.82, 0.78), (0.55, 0.54, 0.52), 0.25, {"tile_w": 12 * INCH_TO_M, "tile_h": 12 * INCH_TO_M, "running_bond": False}),
    "tile_18": ("TILE", (0.85, 0.83, 0.79), (0.55, 0.54, 0.52), 0.24, {"tile_w": 18 * INCH_TO_M, "tile_h": 18 * INCH_TO_M, "running_bond": False}),
    "tile_24": ("TILE", (0.86, 0.84, 0.81), (0.56, 0.55, 0.53), 0.22, {"tile_w": 24 * INCH_TO_M, "tile_h": 24 * INCH_TO_M, "running_bond": False}),
    "tile_offset_half": ("TILE", (0.82, 0.81, 0.79), (0.52, 0.52, 0.51), 0.25, {"tile_w": 24 * INCH_TO_M, "tile_h": 12 * INCH_TO_M, "running_bond": True}),
    "tile_offset_third": ("TILE", (0.83, 0.82, 0.79), (0.52, 0.52, 0.51), 0.25, {"tile_w": 24 * INCH_TO_M, "tile_h": 12 * INCH_TO_M, "running_bond": True}),
    "tile_hex": ("TILE", (0.86, 0.86, 0.84), (0.52, 0.52, 0.52), 0.25, {"tile_w": 8 * INCH_TO_M, "tile_h": 8 * INCH_TO_M, "running_bond": True}),
    "tile_basketweave": ("TILE", (0.85, 0.84, 0.81), (0.52, 0.52, 0.52), 0.25, {"tile_w": 8 * INCH_TO_M, "tile_h": 8 * INCH_TO_M, "running_bond": True}),
    "carpet_stipple": ("SOLID", (0.68, 0.63, 0.56), None, 0.92, {}),
    "carpet_weave": ("SOLID", (0.60, 0.56, 0.50), None, 0.92, {}),
    "concrete_stipple": ("SOLID", (0.56, 0.56, 0.55), None, 0.82, {}),
}


def _get_or_create_floor_material(pr: ParsedRoom, surface_materials):
    import bpy

    pat = (pr.floor_pattern or "none").strip().lower()
    if pat in ("none", "") or pat not in _FLOOR_PATTERN_PRESETS:
        ft = (pr.floor_type or "").lower()
        if "carpet" in ft:
            pat = "carpet_stipple"
        elif "tile" in ft or "porcelain" in ft or "ceramic" in ft:
            pat = "tile_18"
        elif "vinyl" in ft or "lvp" in ft or "laminate" in ft:
            pat = "vinyl_plank"
        elif "hardwood" in ft or "wood" in ft or "oak" in ft:
            pat = "wood_plank"
        elif "concrete" in ft or "garage" in ft or pr.is_slab:
            pat = "concrete_stipple"
        else:
            pat = "wood_plank"

    mat_id = f"EstiSketch_Floor_{pat}"
    existing = bpy.data.materials.get(mat_id)
    if existing is not None:
        return existing

    style, base_srgb, accent_srgb, rough, extra = _FLOOR_PATTERN_PRESETS[pat]
    mat = surface_materials.build_surface_material(
        mat_id, style, base_srgb, accent_srgb, rough, **extra
    )
    mat.diffuse_color = (*base_srgb, 1.0)
    return mat


def _build_floor_mesh(
    name: str,
    points_m: List[Tuple[float, float]],
    z_top: float,
    thickness_m: float,
    target_col,
    is_slab: bool,
    mat=None,
    pattern_rotation_deg: float = 0.0,
    pattern_scale: float = 1.0,
):
    import bmesh
    import bpy
    from mathutils import Vector

    cleaned: List[Tuple[float, float]] = []
    for pt in points_m:
        if not cleaned or math.hypot(pt[0] - cleaned[-1][0], pt[1] - cleaned[-1][1]) > 1e-4:
            cleaned.append(pt)
    if len(cleaned) >= 2 and math.hypot(cleaned[0][0] - cleaned[-1][0], cleaned[0][1] - cleaned[-1][1]) <= 1e-4:
        cleaned.pop()
    if len(cleaned) < 3:
        return None

    bm = bmesh.new()
    verts = [bm.verts.new((x, y, z_top)) for x, y in cleaned]
    bm.verts.ensure_lookup_table()
    edges = [bm.edges.new((verts[i], verts[(i + 1) % len(verts)])) for i in range(len(verts))]
    bmesh.ops.triangle_fill(bm, use_beauty=True, use_dissolve=False, edges=edges)
    bm.normal_update()

    for face in bm.faces:
        if face.normal.z < 0:
            face.normal_flip()

    top_faces = list(bm.faces)
    if top_faces:
        res = bmesh.ops.extrude_face_region(bm, geom=top_faces)
        ext_verts = [g for g in res["geom"] if isinstance(g, bmesh.types.BMVert)]
        bmesh.ops.translate(bm, verts=ext_verts, vec=Vector((0.0, 0.0, -thickness_m)))
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
        bm.normal_update()

    rot_rad = math.radians(pattern_rotation_deg)
    cr_rot, sr_rot = math.cos(rot_rad), math.sin(rot_rad)
    inv_scale = 1.0 / max(0.25, pattern_scale)

    uv_layer = bm.loops.layers.uv.new("UVMap")
    for face in bm.faces:
        for loop in face.loops:
            vx, vy = loop.vert.co.x, loop.vert.co.y
            u = (vx * cr_rot - vy * sr_rot) * inv_scale
            v = (vx * sr_rot + vy * cr_rot) * inv_scale
            loop[uv_layer].uv = (u, v)

    mesh = bpy.data.meshes.new(name)
    bm.to_mesh(mesh)
    bm.free()

    if mat is not None:
        mesh.materials.append(mat)

    obj = bpy.data.objects.new(name, mesh)
    obj["IS_FLOOR_BP"] = True
    if is_slab:
        obj["IS_SLAB"] = True
    obj.color = mat.diffuse_color if mat is not None else (0.72, 0.72, 0.70, 1.0)
    target_col.objects.link(obj)
    return obj


def _clean_points_m(points_m: List[Tuple[float, float]]) -> List[Tuple[float, float]]:
    cleaned: List[Tuple[float, float]] = []
    for pt in points_m:
        if not cleaned or math.hypot(pt[0] - cleaned[-1][0], pt[1] - cleaned[-1][1]) > 1e-4:
            cleaned.append(pt)
    if len(cleaned) >= 2 and math.hypot(cleaned[0][0] - cleaned[-1][0], cleaned[0][1] - cleaned[-1][1]) <= 1e-4:
        cleaned.pop()
    return cleaned


def _build_ceiling_mesh(
    name: str,
    points_m: List[Tuple[float, float]],
    z_bottom: float,
    thickness_m: float,
    target_col,
    scene,
):
    import bmesh
    import bpy
    from mathutils import Vector

    cleaned = _clean_points_m(points_m)
    if len(cleaned) < 3:
        return None

    bm = bmesh.new()
    verts = [bm.verts.new((x, y, z_bottom)) for x, y in cleaned]
    bm.verts.ensure_lookup_table()
    edges = [bm.edges.new((verts[i], verts[(i + 1) % len(verts)])) for i in range(len(verts))]
    bmesh.ops.triangle_fill(bm, use_beauty=True, use_dissolve=False, edges=edges)
    bm.normal_update()

    for face in bm.faces:
        if face.normal.z > 0:
            face.normal_flip()

    bottom_faces = list(bm.faces)
    if bottom_faces:
        res = bmesh.ops.extrude_face_region(bm, geom=bottom_faces)
        ext_verts = [g for g in res["geom"] if isinstance(g, bmesh.types.BMVert)]
        bmesh.ops.translate(bm, verts=ext_verts, vec=Vector((0.0, 0.0, thickness_m)))
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
        bm.normal_update()

    uv_layer = bm.loops.layers.uv.new("UVMap")
    for face in bm.faces:
        for loop in face.loops:
            loop[uv_layer].uv = (loop.vert.co.x, loop.vert.co.y)

    mesh = bpy.data.meshes.new(name)
    bm.to_mesh(mesh)
    bm.free()

    mat = getattr(scene.home_builder, "wall_material", None)
    if mat is not None:
        mesh.materials.append(mat)

    obj = bpy.data.objects.new(name, mesh)
    obj["IS_CEILING_BP"] = True
    obj.color = (0.95, 0.95, 0.94, 1.0)
    target_col.objects.link(obj)
    return obj


def _get_or_create_roof_material(material_name: str):
    import bpy

    key = (material_name or "asphalt_shingle").lower()
    mat_id = f"EstiSketch_Roof_{key}"
    existing = bpy.data.materials.get(mat_id)
    if existing is not None:
        return existing

    presets = {
        "asphalt_shingle": ((0.14, 0.15, 0.17, 1.0), 0.0, 0.85),
        "standing_seam_metal": ((0.20, 0.22, 0.24, 1.0), 0.75, 0.32),
        "metal": ((0.20, 0.22, 0.24, 1.0), 0.75, 0.32),
        "tile": ((0.52, 0.24, 0.15, 1.0), 0.0, 0.65),
        "clay_tile": ((0.52, 0.24, 0.15, 1.0), 0.0, 0.65),
        "wood_shake": ((0.36, 0.27, 0.19, 1.0), 0.0, 0.85),
    }
    base_col, metallic, roughness = presets.get(key, ((0.22, 0.23, 0.25, 1.0), 0.0, 0.75))

    mat = bpy.data.materials.new(name=mat_id)
    if mat.node_tree is None:
        mat.use_nodes = True
    bsdf = next((n for n in mat.node_tree.nodes if n.type == "BSDF_PRINCIPLED"), None)
    if bsdf is not None:
        bsdf.inputs["Base Color"].default_value = base_col
        bsdf.inputs["Metallic"].default_value = metallic
        bsdf.inputs["Roughness"].default_value = roughness
    mat.diffuse_color = base_col
    return mat


def _build_roof_mesh(
    name: str,
    solved: SolvedRoofGeometry,
    cx: float,
    cy: float,
    target_col,
    roof_thickness_in: float = 8.0,
):
    import bmesh
    import bpy
    from mathutils import Vector

    if not solved.facets:
        return None

    bm = bmesh.new()
    vert_cache: Dict[Tuple[int, int, int], object] = {}

    def _get_bm_vert(x_in: float, y_in: float, z_in: float):
        xm, ym = inches_to_blender_xy(x_in, y_in, cx, cy)
        zm = z_in * INCH_TO_M
        key = (round(xm * 10000), round(ym * 10000), round(zm * 10000))
        v = vert_cache.get(key)
        if v is None:
            v = bm.verts.new((xm, ym, zm))
            vert_cache[key] = v
        return v

    for facet in solved.facets:
        f_verts = [_get_bm_vert(x, y, z) for x, y, z in facet.vertices_3d]
        dedup: List[object] = []
        for v in f_verts:
            if not dedup or dedup[-1] != v:
                dedup.append(v)
        if len(dedup) >= 2 and dedup[0] == dedup[-1]:
            dedup.pop()
        if len(dedup) < 3:
            continue

        # Check planarity for quads/ngons; fan-triangulate if non-planar > 2mm
        needs_tri = False
        if len(dedup) > 3:
            p0, p1, p2 = dedup[0].co, dedup[1].co, dedup[2].co
            n = (p1 - p0).cross(p2 - p0)
            nlen = n.length
            if nlen > 1e-6:
                n_unit = n / nlen
                if any(abs((v.co - p0).dot(n_unit)) > 0.002 for v in dedup[3:]):
                    needs_tri = True

        polys = (
            [[dedup[0], dedup[i], dedup[i + 1]] for i in range(1, len(dedup) - 1)]
            if needs_tri
            else [dedup]
        )
        for poly in polys:
            try:
                f = bm.faces.new(poly)
            except ValueError:
                continue
            f.normal_update()
            if f.normal.z < 0:
                f.normal_flip()

    bm.normal_update()
    top_faces = list(bm.faces)
    if not top_faces:
        bm.free()
        return None

    thick_m = max(0.05, roof_thickness_in * INCH_TO_M)
    res = bmesh.ops.extrude_face_region(bm, geom=top_faces)
    ext_verts = [g for g in res["geom"] if isinstance(g, bmesh.types.BMVert)]
    bmesh.ops.translate(bm, verts=ext_verts, vec=Vector((0.0, 0.0, thick_m)))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    bm.normal_update()

    uv_layer = bm.loops.layers.uv.new("UVMap")
    for face in bm.faces:
        is_side = abs(face.normal.z) < 0.25
        for loop in face.loops:
            co = loop.vert.co
            loop[uv_layer].uv = (co.x + co.y, co.z) if is_side else (co.x, co.y)

    mesh = bpy.data.meshes.new(name)
    bm.to_mesh(mesh)
    bm.free()

    mat = _get_or_create_roof_material(solved.material)
    mesh.materials.append(mat)

    obj = bpy.data.objects.new(name, mesh)
    obj["IS_ROOF_BP"] = True
    obj["ESTISKETCH_ID"] = solved.roof_id
    obj["ROOF_MATERIAL"] = solved.material
    obj.color = mat.diffuse_color
    target_col.objects.link(obj)
    return obj


def _build_gable_infill_mesh(
    name: str,
    infill: SolvedGableInfill,
    cx: float,
    cy: float,
    target_col,
    scene,
    mat=None,
):
    import bmesh
    import bpy

    ax, ay = inches_to_blender_xy(infill.p_start[0], infill.p_start[1], cx, cy)
    bx, by = inches_to_blender_xy(infill.p_end[0], infill.p_end[1], cx, cy)
    px, py = inches_to_blender_xy(infill.p_peak[0], infill.p_peak[1], cx, cy)

    dx, dy = bx - ax, by - ay
    seg_len = math.hypot(dx, dy)
    if seg_len < 1e-4:
        return None
    nx, ny = -dy / seg_len, dx / seg_len
    half_t = max(0.01, (infill.thickness * INCH_TO_M) / 2.0)
    zb = infill.z_base * INCH_TO_M
    zp = infill.z_peak * INCH_TO_M

    bm = bmesh.new()
    f0 = bm.verts.new((ax - half_t * nx, ay - half_t * ny, zb))
    f1 = bm.verts.new((bx - half_t * nx, by - half_t * ny, zb))
    f2 = bm.verts.new((px - half_t * nx, py - half_t * ny, zp))
    b0 = bm.verts.new((ax + half_t * nx, ay + half_t * ny, zb))
    b1 = bm.verts.new((bx + half_t * nx, by + half_t * ny, zb))
    b2 = bm.verts.new((px + half_t * nx, py + half_t * ny, zp))

    bm.faces.new((f0, f1, f2))
    bm.faces.new((b1, b0, b2))
    bm.faces.new((f0, b0, b1, f1))
    bm.faces.new((f1, b1, b2, f2))
    bm.faces.new((f2, b2, b0, f0))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])

    uv_layer = bm.loops.layers.uv.new("UVMap")
    for face in bm.faces:
        for loop in face.loops:
            co = loop.vert.co
            loop[uv_layer].uv = (co.x + co.y, co.z)

    mesh = bpy.data.meshes.new(name)
    bm.to_mesh(mesh)
    bm.free()

    use_mat = mat if mat is not None else getattr(scene.home_builder, "wall_material", None)
    if use_mat is not None:
        mesh.materials.append(use_mat)

    obj = bpy.data.objects.new(name, mesh)
    obj["IS_GABLE_INFILL"] = True
    obj.color = use_mat.diffuse_color if use_mat is not None else (0.85, 0.85, 0.83, 1.0)
    target_col.objects.link(obj)
    return obj


def _build_wall_baseboards(
    pw: ParsedWall,
    hb_wall,
    seg_len_m: float,
    door_intervals: List[Tuple[float, float]],
    target_col,
    name: str,
):
    import bmesh
    import bpy

    if not pw.left_baseboard and not pw.right_baseboard:
        return None
    spans = compute_baseboard_spans(seg_len_m, door_intervals)
    if not spans:
        return None

    bb_h = 4.5 * INCH_TO_M
    bb_t = 0.625 * INCH_TO_M
    thick_m = max(0.02, hb_wall.get_input("Thickness"))

    bm = bmesh.new()
    for x0, x1 in spans:
        if pw.left_baseboard:
            _bm_add_box(bm, x0, -bb_t, 0.0, x1, 0.0, bb_h)
        if pw.right_baseboard:
            _bm_add_box(bm, x0, thick_m, 0.0, x1, thick_m + bb_t, bb_h)

    if not bm.faces:
        bm.free()
        return None

    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    uv_layer = bm.loops.layers.uv.new("UVMap")
    for face in bm.faces:
        for loop in face.loops:
            co = loop.vert.co
            loop[uv_layer].uv = (co.x, co.z)

    mesh = bpy.data.meshes.new(name)
    bm.to_mesh(mesh)
    bm.free()

    trim_mat = _get_or_create_simple_material(
        "EstiSketch_Trim_Baseboard", (0.95, 0.95, 0.94, 1.0), metallic=0.0, roughness=0.35
    )
    mesh.materials.append(trim_mat)

    obj = bpy.data.objects.new(name, mesh)
    obj.parent = hb_wall.obj
    obj.location = (0.0, 0.0, 0.0)
    obj["IS_BASEBOARD"] = True
    obj["ESTISKETCH_ID"] = pw.identifier
    obj.color = trim_mat.diffuse_color
    target_col.objects.link(obj)
    return obj


def _build_footer_mesh_from_polys(
    pw: ParsedWall,
    polys_m: List[List[Tuple[float, float]]],
    lvl: ParsedLevel,
    target_col,
    surface_materials,
):
    """Build a single concrete footer object from pre-mitered 2D strip polygons."""
    import bmesh
    import bpy

    z_top = lvl.elevation * INCH_TO_M
    z_bot = z_top - max(0.05, pw.footer_depth * INCH_TO_M)
    bm = bmesh.new()
    for poly in polys_m:
        if len(poly) >= 3:
            _extrude_prism_z(bm, poly, z_bot, z_top)

    if not bm.faces:
        bm.free()
        return None

    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    uv_layer = bm.loops.layers.uv.new("UVMap")
    for face in bm.faces:
        for loop in face.loops:
            co = loop.vert.co
            loop[uv_layer].uv = (co.x, co.y)

    mesh = bpy.data.meshes.new(f"Footer_{pw.identifier}")
    bm.to_mesh(mesh)
    bm.free()

    mat_id = "EstiSketch_Concrete_Footer"
    mat = bpy.data.materials.get(mat_id)
    if mat is None:
        mat = surface_materials.build_surface_material(
            mat_id, "SOLID", (0.52, 0.52, 0.51), None, 0.88
        )
        mat.diffuse_color = (0.52, 0.52, 0.51, 1.0)
    mesh.materials.append(mat)

    obj = bpy.data.objects.new(f"Footer_{pw.identifier}", mesh)
    obj["IS_FOOTER_BP"] = True
    obj["ESTISKETCH_ID"] = pw.identifier
    obj.color = mat.diffuse_color
    target_col.objects.link(obj)
    return obj


def _build_level_footers(
    project: ParsedProject,
    level_by_id: Dict[str, ParsedLevel],
    cx: float,
    cy: float,
    target_col,
    surface_materials,
) -> int:
    """Build mitered footers grouped by ``(level_id, footer_depth)``."""
    groups: Dict[Tuple[str, float], List[ParsedWall]] = {}
    for pw in project.walls:
        if pw.footer:
            groups.setdefault((pw.level_id, round(pw.footer_depth, 3)), []).append(pw)

    footer_count = 0
    for (lvl_id, _), group_walls in groups.items():
        lvl = level_by_id.get(lvl_id, project.levels[0])
        segs: List[StripSegment] = []
        seg_ranges: List[Tuple[ParsedWall, int, int]] = []
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
            for i in range(len(pts_m) - 1):
                segs.append(StripSegment(pts_m[i], pts_m[i + 1], y0, y1))
            seg_ranges.append((pw, start_idx, len(segs)))

        polys = compute_mitered_strip_polygons(segs)
        for pw, s_idx, e_idx in seg_ranges:
            f_obj = _build_footer_mesh_from_polys(
                pw, polys[s_idx:e_idx], lvl, target_col, surface_materials
            )
            if f_obj is not None:
                footer_count += 1
    return footer_count


def _build_level_rim_bands(
    project: ParsedProject,
    level_by_id: Dict[str, ParsedLevel],
    level_cols: Dict[str, Dict[str, object]],
    cx: float,
    cy: float,
    scene,
    surface_materials,
) -> int:
    """Build exterior rim-joist band walls covering upper-level floor slab edges."""
    import bmesh
    import bpy

    fallback = getattr(scene.home_builder, "wall_material", None)
    rim_count = 0
    for lvl in project.levels:
        if lvl.elevation <= 0.1 or lvl.floor_thickness <= 0.01:
            continue
        ext_walls = [
            pw
            for pw in project.walls
            if pw.level_id == lvl.id and pw.exterior_wall and not pw.symbolic
        ]
        if not ext_walls:
            continue

        z_top = lvl.elevation * INCH_TO_M
        z_bot = (lvl.elevation - lvl.floor_thickness) * INCH_TO_M
        segs: List[StripSegment] = []
        seg_ranges: List[Tuple[ParsedWall, int, int]] = []
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
            for i in range(len(pts_m) - 1):
                segs.append(StripSegment(pts_m[i], pts_m[i + 1], 0.0, thick_m))
            seg_ranges.append((pw, start_idx, len(segs)))

        polys = compute_mitered_strip_polygons(segs)
        walls_col = level_cols[lvl.id]["walls"]
        for pw, s_idx, e_idx in seg_ranges:
            bm = bmesh.new()
            for poly in polys[s_idx:e_idx]:
                if len(poly) >= 3:
                    _extrude_prism_z(bm, poly, z_bot, z_top)
            if not bm.faces:
                bm.free()
                continue

            bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
            p0_m = segs[s_idx].p0 if s_idx < len(segs) else (0.0, 0.0)
            p1_m = segs[e_idx - 1].p1 if e_idx > s_idx else (1.0, 0.0)
            wdx, wdy = p1_m[0] - p0_m[0], p1_m[1] - p0_m[1]
            wlen = math.hypot(wdx, wdy) or 1.0
            ux, uy = wdx / wlen, wdy / wlen

            uv_layer = bm.loops.layers.uv.new("UVMap")
            for face in bm.faces:
                is_side = abs(face.normal.z) < 0.25
                for loop in face.loops:
                    co = loop.vert.co
                    if is_side:
                        along_m = (co.x - p0_m[0]) * ux + (co.y - p0_m[1]) * uy
                        loop[uv_layer].uv = (along_m, co.z)
                    else:
                        loop[uv_layer].uv = (co.x, co.y)

            mesh = bpy.data.meshes.new(f"RimBand_{pw.identifier}")
            bm.to_mesh(mesh)
            bm.free()

            _, rf = _resolve_wall_side_finishes(pw)
            ext_mat = _get_or_create_wall_finish_material(
                rf, pw.right_color, surface_materials, fallback
            )
            if ext_mat is not None:
                mesh.materials.append(ext_mat)

            obj = bpy.data.objects.new(f"RimBand_{pw.identifier}", mesh)
            obj["IS_RIM_BAND"] = True
            obj["ESTISKETCH_ID"] = pw.identifier
            obj["ESTISKETCH_LEVEL"] = lvl.id
            if ext_mat is not None:
                obj.color = ext_mat.diffuse_color
            walls_col.objects.link(obj)
            rim_count += 1
    return rim_count


def _build_wall_footer(
    pw: ParsedWall,
    lvl: ParsedLevel,
    cx: float,
    cy: float,
    target_col,
    surface_materials,
):
    if not pw.footer:
        return None
    return _build_level_footers(
        ParsedProject(levels=[lvl], walls=[pw]),
        {lvl.id: lvl},
        cx,
        cy,
        target_col,
        surface_materials,
    )


def _build_garage_door_mesh(
    cage_obj,
    width_m: float,
    thickness_m: float,
    height_m: float,
    openings_col,
    hb_wall_obj,
):
    import bmesh
    import bpy

    # Create a dedicated boolean cutter inside the cage matching reveal depth
    cutter_bm = bmesh.new()
    reveal_pad = 0.02
    _bm_add_box(
        cutter_bm,
        0.0,
        -reveal_pad,
        -0.01,
        width_m,
        thickness_m + reveal_pad,
        height_m,
    )
    bmesh.ops.recalc_face_normals(cutter_bm, faces=cutter_bm.faces[:])
    cutter_mesh = bpy.data.meshes.new(f"{cage_obj.name}_Cutter")
    cutter_bm.to_mesh(cutter_mesh)
    cutter_bm.free()
    cutter_obj = bpy.data.objects.new(f"{cage_obj.name}_Cutter", cutter_mesh)
    cutter_obj.parent = cage_obj
    cutter_obj.display_type = "WIRE"
    cutter_obj.hide_viewport = True
    cutter_obj.hide_render = True
    openings_col.objects.link(cutter_obj)
    _add_boolean_cut(hb_wall_obj, cutter_obj)

    frame_mat = _get_or_create_simple_material(
        "EstiSketch_Garage_Frame", (0.86, 0.86, 0.85, 1.0), metallic=0.15, roughness=0.38
    )
    panel_mat = _get_or_create_simple_material(
        "EstiSketch_Garage_Panel", (0.93, 0.93, 0.91, 1.0), metallic=0.05, roughness=0.40
    )
    glass_mat = _get_or_create_simple_material(
        "EstiSketch_Garage_Glass", (0.68, 0.80, 0.88, 1.0), metallic=0.0, roughness=0.08, alpha=0.55
    )
    seal_mat = _get_or_create_simple_material(
        "EstiSketch_DarkMetal", (0.14, 0.14, 0.15, 1.0), metallic=0.5, roughness=0.45
    )

    bm = bmesh.new()
    jamb_w = 0.045
    # Perimeter jamb & header trim (mat 0)
    _bm_add_box(bm, 0.0, 0.0, 0.0, jamb_w, thickness_m, height_m, mat_index=0)
    _bm_add_box(bm, width_m - jamb_w, 0.0, 0.0, width_m, thickness_m, height_m, mat_index=0)
    _bm_add_box(bm, jamb_w, 0.0, height_m - jamb_w, width_m - jamb_w, thickness_m, height_m, mat_index=0)

    # Door leaf recessed near center-outside of wall (y in [0.03, 0.08])
    y_back = min(thickness_m * 0.45, max(0.02, thickness_m - 0.055))
    y_front = y_back + 0.045
    seal_h = 0.03
    _bm_add_box(bm, jamb_w, y_back, 0.0, width_m - jamb_w, y_front, seal_h, mat_index=3)

    inner_x0 = jamb_w
    inner_x1 = width_m - jamb_w
    inner_w = max(0.2, inner_x1 - inner_x0)
    inner_z0 = seal_h
    inner_z1 = height_m - jamb_w
    n_sections = 4
    sec_h = (inner_z1 - inner_z0) / n_sections
    gap = 0.008

    for s_idx in range(n_sections):
        sz0 = inner_z0 + s_idx * sec_h + gap * 0.5
        sz1 = inner_z0 + (s_idx + 1) * sec_h - gap * 0.5
        _bm_add_box(bm, inner_x0, y_back, sz0, inner_x1, y_front, sz1, mat_index=1)
        if s_idx < n_sections - 1:
            # Horizontal raised stiles / carriage embosses on outer face (+Y)
            n_cols = 4 if inner_w > 3.2 else 2
            col_w = inner_w / n_cols
            pad_x = 0.08
            pad_z = 0.06
            for ci in range(n_cols):
                px0 = inner_x0 + ci * col_w + pad_x
                px1 = inner_x0 + (ci + 1) * col_w - pad_x
                if px1 > px0 + 0.05 and sz1 - sz0 > 2 * pad_z + 0.04:
                    _bm_add_box(
                        bm, px0, y_front, sz0 + pad_z, px1, y_front + 0.012, sz1 - pad_z, mat_index=1
                    )
        else:
            # Top row carriage-house glass lites (mat 2)
            n_lites = 4 if inner_w > 3.2 else 2
            lite_w = inner_w / n_lites
            pad_x = 0.09
            pad_z = 0.08
            for li in range(n_lites):
                gx0 = inner_x0 + li * lite_w + pad_x
                gx1 = inner_x0 + (li + 1) * lite_w - pad_x
                if gx1 > gx0 + 0.05 and sz1 - sz0 > 2 * pad_z + 0.04:
                    _bm_add_box(
                        bm, gx0, y_front - 0.004, sz0 + pad_z, gx1, y_front + 0.008, sz1 - pad_z, mat_index=2
                    )

    door_obj = _finalize_bmesh_object(
        bm,
        f"GarageDoor_{cage_obj.name}",
        [frame_mat, panel_mat, glass_mat, seal_mat],
        (0.0, 0.0, 0.0),
        0.0,
        openings_col,
        cage_obj.get("ESTISKETCH_ID", ""),
    )
    door_obj.parent = cage_obj
    door_obj["IS_DOOR_WINDOW_GEO"] = True
    return door_obj, cutter_obj


def _get_or_create_stair_material(
    mat_id: str,
    base_col: Tuple[float, float, float, float],
    metallic: float = 0.0,
    roughness: float = 0.45,
):
    import bpy

    existing = bpy.data.materials.get(mat_id)
    if existing is not None:
        return existing
    mat = bpy.data.materials.new(name=mat_id)
    if mat.node_tree is None:
        mat.use_nodes = True
    bsdf = next((n for n in mat.node_tree.nodes if n.type == "BSDF_PRINCIPLED"), None)
    if bsdf is not None:
        bsdf.inputs["Base Color"].default_value = base_col
        bsdf.inputs["Metallic"].default_value = metallic
        bsdf.inputs["Roughness"].default_value = roughness
    mat.diffuse_color = base_col
    return mat


def _apply_slab_cutouts(
    slab_obj,
    cutout_polys_in: List[List[Tuple[float, float]]],
    z_min_m: float,
    z_max_m: float,
    cx: float,
    cy: float,
    scene,
) -> int:
    """Boolean-cut and bake vertical hole prisms out of a floor or ceiling slab."""
    import bmesh
    import bpy
    from mathutils import Vector

    if slab_obj is None or not cutout_polys_in:
        return 0

    cutters = []
    z_lo = z_min_m - 0.15
    z_hi = z_max_m + 0.15
    for idx, poly_in in enumerate(cutout_polys_in):
        pts_m = _clean_points_m([inches_to_blender_xy(x, y, cx, cy) for x, y in poly_in])
        if len(pts_m) < 3:
            continue
        bm = bmesh.new()
        verts = [bm.verts.new((x, y, z_lo)) for x, y in pts_m]
        bm.verts.ensure_lookup_table()
        edges = [bm.edges.new((verts[i], verts[(i + 1) % len(verts)])) for i in range(len(verts))]
        bmesh.ops.triangle_fill(bm, use_beauty=True, use_dissolve=False, edges=edges)
        bm.normal_update()
        for f in bm.faces:
            if f.normal.z > 0:
                f.normal_flip()
        res = bmesh.ops.extrude_face_region(bm, geom=list(bm.faces))
        ext_verts = [g for g in res["geom"] if isinstance(g, bmesh.types.BMVert)]
        bmesh.ops.translate(bm, verts=ext_verts, vec=Vector((0.0, 0.0, z_hi - z_lo)))
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
        c_mesh = bpy.data.meshes.new(f"_CutPrism_{slab_obj.name}_{idx}")
        bm.to_mesh(c_mesh)
        bm.free()

        c_obj = bpy.data.objects.new(f"_CutPrism_{slab_obj.name}_{idx}", c_mesh)
        scene.collection.objects.link(c_obj)
        mod = slab_obj.modifiers.new(name=f"HoleCut_{idx}", type="BOOLEAN")
        mod.operation = "DIFFERENCE"
        mod.object = c_obj
        mod.solver = "EXACT"
        cutters.append((c_obj, c_mesh))

    if not cutters:
        return 0

    bpy.context.view_layer.update()
    depsgraph = bpy.context.evaluated_depsgraph_get()
    eval_obj = slab_obj.evaluated_get(depsgraph)
    baked_mesh = bpy.data.meshes.new_from_object(eval_obj, depsgraph=depsgraph)
    old_mesh = slab_obj.data
    slab_obj.data = baked_mesh
    slab_obj.modifiers.clear()
    if old_mesh is not None and old_mesh.users == 0:
        bpy.data.meshes.remove(old_mesh)

    for c_obj, c_mesh in cutters:
        bpy.data.objects.remove(c_obj, do_unlink=True)
        if c_mesh.users == 0:
            bpy.data.meshes.remove(c_mesh)
    return len(cutters)


def _extrude_prism_z(bm, pts_m: List[Tuple[float, float]], z_bot: float, z_top: float) -> None:
    from mathutils import Vector
    import bmesh

    if len(pts_m) < 3 or z_top <= z_bot + 1e-5:
        return
    verts = [bm.verts.new((x, y, z_bot)) for x, y in pts_m]
    bm.verts.ensure_lookup_table()
    edges = [bm.edges.new((verts[i], verts[(i + 1) % len(verts)])) for i in range(len(verts))]
    res_fill = bmesh.ops.triangle_fill(bm, use_beauty=True, use_dissolve=False, edges=edges)
    faces = [g for g in res_fill.get("geom", []) if isinstance(g, bmesh.types.BMFace)]
    if not faces:
        return
    for f in faces:
        f.normal_update()
        if f.normal.z > 0:
            f.normal_flip()
    res = bmesh.ops.extrude_face_region(bm, geom=faces)
    ext_verts = [g for g in res["geom"] if isinstance(g, bmesh.types.BMVert)]
    bmesh.ops.translate(bm, verts=ext_verts, vec=Vector((0.0, 0.0, z_top - z_bot)))


def _build_l_winder_stair_mesh(ps: ParsedStair, z_start_in: float, cx: float, cy: float):
    import bmesh
    import bpy

    lay = _l_stair_layout_in(
        ps.num_steps,
        ps.steps_before_landing,
        ps.tread_depth,
        ps.landing_depth,
        ps.width,
        ps.winder_count,
    )
    sb = int(lay["steps_before"])
    sa_cnt = int(lay["steps_after"])
    wc = int(lay["winder_count"])
    total_steps = max(1, sb + wc + sa_cnt)
    riser_in = ps.total_rise / total_steps
    tread_thick_in = 1.5
    width = max(12.0, ps.width)
    hw = width / 2.0
    ang = ps.direction_angle
    ca, sa = math.cos(ang), math.sin(ang)
    sx, sy = ps.start_point

    def _to_m(u: float, v: float) -> Tuple[float, float]:
        return inches_to_blender_xy(sx + u * ca - v * sa, sy + u * sa + v * ca, cx, cy)

    bm = bmesh.new()

    # Flight 1 treads + risers
    for i in range(sb):
        u0 = i * ps.tread_depth
        u1 = (i + 1) * ps.tread_depth
        z_top = (z_start_in + (i + 1) * riser_in) * INCH_TO_M
        z_bot = (z_start_in + i * riser_in) * INCH_TO_M
        pts_m = [_to_m(u0, -hw), _to_m(u1, -hw), _to_m(u1, hw), _to_m(u0, hw)]
        _extrude_prism_z(bm, pts_m, max(z_start_in * INCH_TO_M, z_bot), z_top)

    # Winder wedge treads in the width x width turn square
    rb = lay["run_before"]
    w_polys = _winder_tread_polys_local(width, wc, ps.turn_direction)
    for wi, wpoly in enumerate(w_polys):
        step_idx = sb + wi
        z_top = (z_start_in + (step_idx + 1) * riser_in) * INCH_TO_M
        z_bot = (z_start_in + step_idx * riser_in - tread_thick_in) * INCH_TO_M
        pts_m = [_to_m(rb + u, -hw + v) for (u, v) in wpoly]
        _extrude_prism_z(bm, pts_m, max(z_start_in * INCH_TO_M, z_bot), z_top)

    # Flight 2 treads + risers after turn square
    sign_v = -1.0 if ps.turn_direction == "left" else 1.0
    for i in range(sa_cnt):
        step_idx = sb + wc + i
        d0 = i * ps.tread_depth
        d1 = (i + 1) * ps.tread_depth
        v0 = sign_v * (hw + d0)
        v1 = sign_v * (hw + d1)
        z_top = (z_start_in + (step_idx + 1) * riser_in) * INCH_TO_M
        z_bot = (z_start_in + step_idx * riser_in - tread_thick_in) * INCH_TO_M
        pts_m = [_to_m(rb, v0), _to_m(rb + width, v0), _to_m(rb + width, v1), _to_m(rb, v1)]
        _extrude_prism_z(bm, pts_m, max(z_start_in * INCH_TO_M, z_bot), z_top)

    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    mesh = bpy.data.meshes.new(f"Stair_{ps.identifier}")
    bm.to_mesh(mesh)
    bm.free()
    return mesh


def _build_spiral_stair_mesh(ps: ParsedStair, z_start_in: float, cx: float, cy: float):
    import bmesh
    import bpy
    from mathutils import Matrix

    bm = bmesh.new()
    sx_m, sy_m = inches_to_blender_xy(ps.start_point[0], ps.start_point[1], cx, cy)
    z0_m = z_start_in * INCH_TO_M
    total_rise_m = max(0.2, ps.total_rise * INCH_TO_M)
    inner_r_m = max(0.05, ps.inner_radius * INCH_TO_M)
    outer_r_m = inner_r_m + max(0.3, ps.width * INCH_TO_M)
    steps = max(4, ps.num_steps)
    riser_m = total_rise_m / steps
    tread_thick_m = 1.5 * INCH_TO_M

    # Center structural pole (extends 36" above top tread)
    pole_h = total_rise_m + 36.0 * INCH_TO_M
    bmesh.ops.create_cone(
        bm,
        cap_ends=True,
        cap_tris=False,
        segments=20,
        radius1=inner_r_m,
        radius2=inner_r_m,
        depth=pole_h,
        matrix=Matrix.Translation((sx_m, sy_m, z0_m + pole_h / 2.0)),
    )

    rot_rad = math.radians(ps.rotation_degrees or 270.0)
    # In Blender XY (Y-flipped), EstiSketch left-turn (-ang) corresponds to +ang_b
    dir_b = 1.0 if ps.turn_direction == "left" else -1.0
    theta0_b = -ps.direction_angle
    dtheta = (rot_rad / steps) * dir_b

    for i in range(steps):
        a0 = theta0_b + i * dtheta
        a1 = theta0_b + (i + 1) * dtheta
        pts_m = [
            (sx_m + inner_r_m * math.cos(a0), sy_m + inner_r_m * math.sin(a0)),
            (sx_m + outer_r_m * math.cos(a0), sy_m + outer_r_m * math.sin(a0)),
            (sx_m + outer_r_m * math.cos(a1), sy_m + outer_r_m * math.sin(a1)),
            (sx_m + inner_r_m * math.cos(a1), sy_m + inner_r_m * math.sin(a1)),
        ]
        z_top = z0_m + (i + 1) * riser_m
        _extrude_prism_z(bm, pts_m, max(z0_m, z_top - tread_thick_m), z_top)

    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    mesh = bpy.data.meshes.new(f"Stair_{ps.identifier}")
    bm.to_mesh(mesh)
    bm.free()
    return mesh


def _build_stair_object(
    ps: ParsedStair,
    start_lvl: ParsedLevel,
    cx: float,
    cy: float,
    target_col,
    ops_stairs,
):
    import bpy

    wood_mat = _get_or_create_stair_material(
        "EstiSketch_Stair_Wood", (0.48, 0.33, 0.20, 1.0), metallic=0.0, roughness=0.45
    )

    use_hb5 = (
        ps.stair_type in ("straight", "u-shaped")
        or (ps.stair_type == "l-shaped" and ps.winder_count == 0)
    )
    if use_hb5:
        width_m = max(0.3, ps.width * INCH_TO_M)
        total_rise_m = max(0.2, ps.total_rise * INCH_TO_M)
        steps = max(1, ps.num_steps)
        riser_m = total_rise_m / steps
        if ps.stair_type == "straight" and ps.total_run > 0.0:
            tread_depth_m = (ps.total_run / steps) * INCH_TO_M
        elif ps.stair_type == "u-shaped":
            before = ps.steps_before_landing if 0 < ps.steps_before_landing < steps else steps // 2
            scale = max(1, before - 1) / max(1, before)
            tread_depth_m = max(0.12, scale * ps.tread_depth * INCH_TO_M)
        else:
            tread_depth_m = max(0.15, ps.tread_depth * INCH_TO_M)
        tread_thick_m = 1.25 * INCH_TO_M
        landing_depth_m = max(width_m, (ps.landing_depth or ps.width) * INCH_TO_M)
        if 0 < ps.steps_before_landing < steps:
            landing_height_m = total_rise_m * (ps.steps_before_landing / steps)
        else:
            landing_height_m = total_rise_m / 2.0
        hb_type = {"straight": "STRAIGHT", "l-shaped": "L_SHAPE", "u-shaped": "U_SHAPE"}[ps.stair_type]
        hb_turn = "LEFT" if ps.turn_direction == "left" else "RIGHT"
        gap_m = max(0.0, ps.inner_radius * INCH_TO_M) if ps.stair_type == "u-shaped" and ps.inner_radius != 6.0 else 0.0

        mesh = ops_stairs.create_stair_mesh(
            width_m,
            total_rise_m,
            riser_m,
            tread_depth_m,
            tread_thick_m,
            hb_type,
            hb_turn,
            landing_depth_m,
            landing_height_m,
            gap_m,
        )
        obj = bpy.data.objects.new(f"Stair_{ps.identifier}", mesh)
        obj["IS_STAIR"] = True
        obj["MENU_ID"] = "HOME_BUILDER_MT_stair_commands"
        obj["STAIR_WIDTH"] = width_m
        obj["STAIR_TOTAL_RISE"] = total_rise_m
        obj["STAIR_RISER_HEIGHT"] = riser_m
        obj["STAIR_TREAD_DEPTH"] = tread_depth_m
        obj["STAIR_TREAD_THICKNESS"] = tread_thick_m
        obj["STAIR_TYPE"] = hb_type
        obj["STAIR_TURN_DIRECTION"] = hb_turn
        obj["STAIR_LANDING_DEPTH"] = landing_depth_m
        obj["STAIR_LANDING_HEIGHT"] = landing_height_m
        obj["STAIR_GAP"] = gap_m
        loc, rot_z = compute_hb5_stair_transform(ps, start_lvl.elevation, cx, cy)
        obj.location = loc
        obj.rotation_euler = (0.0, 0.0, rot_z)
    elif ps.stair_type == "l-shaped":
        mesh = _build_l_winder_stair_mesh(ps, start_lvl.elevation, cx, cy)
        obj = bpy.data.objects.new(f"Stair_{ps.identifier}", mesh)
        obj["IS_STAIR"] = True
    else:
        mesh = _build_spiral_stair_mesh(ps, start_lvl.elevation, cx, cy)
        obj = bpy.data.objects.new(f"Stair_{ps.identifier}", mesh)
        obj["IS_STAIR"] = True

    obj["ESTISKETCH_ID"] = ps.identifier
    obj.data.materials.append(wood_mat)
    obj.color = wood_mat.diffuse_color
    target_col.objects.link(obj)
    return obj


def _build_stair_railing_mesh(
    name: str,
    paths_3d_in: List[List[Tuple[float, float, float]]],
    rail_height_in: float,
    cx: float,
    cy: float,
    target_col,
):
    import bmesh
    import bpy

    if not paths_3d_in:
        return None

    bm = bmesh.new()
    rail_h_m = max(0.5, rail_height_in * INCH_TO_M)
    post_r = (3.5 * INCH_TO_M) / 2.0
    bal_r = (1.25 * INCH_TO_M) / 2.0
    bal_step_m = 4.5 * INCH_TO_M
    rail_hw = (2.25 * INCH_TO_M) / 2.0
    rail_ht = 1.75 * INCH_TO_M

    def _add_post(px: float, py: float, pz0: float, pz1: float, half_r: float) -> None:
        pts = [
            (px - half_r, py - half_r),
            (px + half_r, py - half_r),
            (px + half_r, py + half_r),
            (px - half_r, py + half_r),
        ]
        _extrude_prism_z(bm, pts, pz0, pz1)

    for path in paths_3d_in:
        if len(path) < 2:
            continue
        pts_m = [
            (*inches_to_blender_xy(x, y, cx, cy), z * INCH_TO_M)
            for x, y, z in path
        ]
        for vx, vy, vz in pts_m:
            _add_post(vx, vy, vz, vz + rail_h_m + 0.04, post_r)

        for i in range(len(pts_m) - 1):
            x0, y0, z0 = pts_m[i]
            x1, y1, z1 = pts_m[i + 1]
            dx, dy, dz = x1 - x0, y1 - y0, z1 - z0
            horiz = math.hypot(dx, dy)
            if horiz < 0.02:
                continue

            # Balusters every ~4.5"
            n_bal = max(0, int(horiz / bal_step_m) - 1)
            for k in range(1, n_bal + 1):
                t = k / (n_bal + 1)
                bx = x0 + t * dx
                by = y0 + t * dy
                bz = z0 + t * dz
                _add_post(bx, by, bz, bz + rail_h_m, bal_r)

            # Sloped top handrail bar
            nx, ny = -dy / horiz, dx / horiz
            b0 = bm.verts.new((x0 + rail_hw * nx, y0 + rail_hw * ny, z0 + rail_h_m - rail_ht))
            b1 = bm.verts.new((x0 - rail_hw * nx, y0 - rail_hw * ny, z0 + rail_h_m - rail_ht))
            b2 = bm.verts.new((x1 - rail_hw * nx, y1 - rail_hw * ny, z1 + rail_h_m - rail_ht))
            b3 = bm.verts.new((x1 + rail_hw * nx, y1 + rail_hw * ny, z1 + rail_h_m - rail_ht))
            t0 = bm.verts.new((x0 + rail_hw * nx, y0 + rail_hw * ny, z0 + rail_h_m))
            t1 = bm.verts.new((x0 - rail_hw * nx, y0 - rail_hw * ny, z0 + rail_h_m))
            t2 = bm.verts.new((x1 - rail_hw * nx, y1 - rail_hw * ny, z1 + rail_h_m))
            t3 = bm.verts.new((x1 + rail_hw * nx, y1 + rail_hw * ny, z1 + rail_h_m))
            for quad in (
                (t0, t1, t2, t3),
                (b3, b2, b1, b0),
                (b0, b1, t1, t0),
                (b1, b2, t2, t1),
                (b2, b3, t3, t2),
                (b3, b0, t0, t3),
            ):
                try:
                    bm.faces.new(quad)
                except ValueError:
                    pass

    if not bm.faces:
        bm.free()
        return None

    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    uv_layer = bm.loops.layers.uv.new("UVMap")
    for face in bm.faces:
        for loop in face.loops:
            co = loop.vert.co
            loop[uv_layer].uv = (co.x + co.y, co.z)

    mesh = bpy.data.meshes.new(name)
    bm.to_mesh(mesh)
    bm.free()

    rail_mat = _get_or_create_stair_material(
        "EstiSketch_Stair_Railing", (0.22, 0.16, 0.12, 1.0), metallic=0.1, roughness=0.4
    )
    mesh.materials.append(rail_mat)
    obj = bpy.data.objects.new(name, mesh)
    obj["IS_STAIR_RAILING"] = True
    obj.color = rail_mat.diffuse_color
    target_col.objects.link(obj)
    return obj


_HB5_CABINET_SYMBOLS = {
    "base_cabinet",
    "base_drawer_cabinet",
    "sink_base_cabinet",
    "corner_base_cabinet",
    "upper_cabinet",
    "corner_upper_cabinet",
    "tall_pantry",
    "island_cabinet",
    "vanity_single",
    "vanity_double",
}

_HB5_APPLIANCE_SYMBOLS = {
    "range_stove",
    "refrigerator",
    "dishwasher",
    "range_hood",
    "microwave",
    "cooktop",
    "wall_oven",
    "kitchen_sink_single",
    "kitchen_sink_double",
    "washer",
    "dryer",
}

_PLUMBING_MECHANICAL_SYMBOLS = {
    "toilet",
    "bathtub",
    "shower_square",
    "shower_corner",
    "pedestal_sink",
    "utility_sink",
    "water_heater",
    "furnace",
    "air_conditioner",
}

_FURNITURE_SYMBOLS = {
    "sofa",
    "loveseat",
    "armchair",
    "coffee_table",
    "end_table",
    "tv_console",
    "bed_king",
    "bed_queen",
    "bed_twin",
    "nightstand",
    "dresser",
    "dining_table",
    "dining_chair",
    "desk",
    "office_chair",
    "bookshelf",
}


def _get_or_create_simple_material(
    mat_id: str,
    base_col: Tuple[float, float, float, float],
    metallic: float = 0.0,
    roughness: float = 0.5,
    alpha: float = 1.0,
):
    import bpy

    existing = bpy.data.materials.get(mat_id)
    if existing is not None:
        return existing
    mat = bpy.data.materials.new(name=mat_id)
    if mat.node_tree is None:
        mat.use_nodes = True
    bsdf = next((n for n in mat.node_tree.nodes if n.type == "BSDF_PRINCIPLED"), None)
    if bsdf is not None:
        bsdf.inputs["Base Color"].default_value = base_col
        bsdf.inputs["Metallic"].default_value = metallic
        bsdf.inputs["Roughness"].default_value = roughness
        if alpha < 0.999 and "Alpha" in bsdf.inputs:
            bsdf.inputs["Alpha"].default_value = alpha
    mat.diffuse_color = (base_col[0], base_col[1], base_col[2], alpha)
    return mat


def _bm_add_box(
    bm,
    x0: float,
    y0: float,
    z0: float,
    x1: float,
    y1: float,
    z1: float,
    mat_index: int = 0,
) -> None:
    if abs(x1 - x0) < 1e-5 or abs(y1 - y0) < 1e-5 or abs(z1 - z0) < 1e-5:
        return
    xa, xb = (x0, x1) if x0 < x1 else (x1, x0)
    ya, yb = (y0, y1) if y0 < y1 else (y1, y0)
    za, zb = (z0, z1) if z0 < z1 else (z1, z0)
    v = [
        bm.verts.new((xa, ya, za)),
        bm.verts.new((xb, ya, za)),
        bm.verts.new((xb, yb, za)),
        bm.verts.new((xa, yb, za)),
        bm.verts.new((xa, ya, zb)),
        bm.verts.new((xb, ya, zb)),
        bm.verts.new((xb, yb, zb)),
        bm.verts.new((xa, yb, zb)),
    ]
    faces = [
        (v[4], v[5], v[6], v[7]),
        (v[3], v[2], v[1], v[0]),
        (v[0], v[1], v[5], v[4]),
        (v[1], v[2], v[6], v[5]),
        (v[2], v[3], v[7], v[6]),
        (v[3], v[0], v[4], v[7]),
    ]
    for fverts in faces:
        f = bm.faces.new(fverts)
        f.material_index = mat_index


def _bm_add_cylinder(
    bm,
    cx: float,
    cy: float,
    z0: float,
    z1: float,
    radius: float,
    segments: int = 20,
    mat_index: int = 0,
) -> None:
    from mathutils import Matrix
    import bmesh

    h = max(1e-4, z1 - z0)
    res = bmesh.ops.create_cone(
        bm,
        cap_ends=True,
        cap_tris=False,
        segments=segments,
        radius1=radius,
        radius2=radius,
        depth=h,
        matrix=Matrix.Translation((cx, cy, z0 + h / 2.0)),
    )
    if mat_index != 0:
        for g in res.get("verts", []):
            for f in g.link_faces:
                f.material_index = mat_index


def _finalize_bmesh_object(
    bm,
    name: str,
    materials: List[object],
    loc: Tuple[float, float, float],
    rot_z: float,
    target_col,
    identifier: str,
):
    import bmesh
    import bpy

    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    uv_layer = bm.loops.layers.uv.new("UVMap")
    for face in bm.faces:
        is_vert = abs(face.normal.z) < 0.25
        for loop in face.loops:
            co = loop.vert.co
            loop[uv_layer].uv = (co.x + co.y, co.z) if is_vert else (co.x, co.y)

    mesh = bpy.data.meshes.new(name)
    bm.to_mesh(mesh)
    bm.free()
    for mat in materials:
        mesh.materials.append(mat)

    obj = bpy.data.objects.new(name, mesh)
    obj.location = loc
    obj.rotation_euler = (0.0, 0.0, rot_z)
    obj["ESTISKETCH_ID"] = identifier
    if materials:
        obj.color = materials[0].diffuse_color
    target_col.objects.link(obj)
    return obj


def _move_hierarchy_to_collection(root_obj, target_col) -> None:
    _move_object_to_collection(root_obj, target_col)
    for child in list(root_obj.children_recursive):
        _move_object_to_collection(child, target_col)


def _build_hb5_cabinet(
    fx: ParsedFixture,
    lvl: ParsedLevel,
    cx: float,
    cy: float,
    target_col,
    types_frameless,
    solver_frameless,
):
    sym = fx.symbol_type
    w_m = max(0.15, fx.width * INCH_TO_M)
    d_m = max(0.15, fx.depth * INCH_TO_M)
    h_m = max(0.15, fx.height * INCH_TO_M)

    if sym == "upper_cabinet":
        cab = types_frameless.UpperCabinet()
        cab.width, cab.depth, cab.height = w_m, d_m, h_m
        cab.create(f"Cabinet_{sym}_{fx.identifier}")
    elif sym == "tall_pantry":
        cab = types_frameless.TallCabinet()
        cab.width, cab.depth, cab.height = w_m, d_m, h_m
        cab.create(f"Cabinet_{sym}_{fx.identifier}")
    elif sym == "corner_base_cabinet":
        cab = types_frameless.PieCutCornerBaseCabinet()
        cab.corner_size = w_m
        cab.depth = 24.0 * INCH_TO_M
        cab.height = h_m
        cab.create(f"Cabinet_{sym}_{fx.identifier}")
        if cab.has_input("Left Depth"):
            cab.set_input("Left Depth", 24.0 * INCH_TO_M)
        if cab.has_input("Right Depth"):
            cab.set_input("Right Depth", 24.0 * INCH_TO_M)
    elif sym == "corner_upper_cabinet":
        cab = types_frameless.PieCutCornerUpperCabinet()
        cab.corner_size = w_m
        cab.depth = 12.0 * INCH_TO_M
        cab.height = h_m
        cab.create(f"Cabinet_{sym}_{fx.identifier}")
        if cab.has_input("Left Depth"):
            cab.set_input("Left Depth", 12.0 * INCH_TO_M)
        if cab.has_input("Right Depth"):
            cab.set_input("Right Depth", 12.0 * INCH_TO_M)
    else:
        cab = types_frameless.BaseCabinet()
        cab.default_exterior = "3 Drawers" if sym == "base_drawer_cabinet" else "Doors"
        cab.width, cab.depth, cab.height = w_m, d_m, h_m
        cab.create(f"Cabinet_{sym}_{fx.identifier}")
        if sym == "sink_base_cabinet":
            try:
                cab.set_property("Base Top Construction", 2)
            except Exception:
                pass

    cab.set_input("Dim X", w_m)
    cab.set_input("Dim Y", d_m if "corner" not in sym else w_m)
    cab.set_input("Dim Z", h_m)
    try:
        solver_frameless.recalculate_cabinet(cab.obj)
    except Exception as exc:
        print(f"Warning: frameless solver recalc skipped for {fx.identifier}: {exc}")

    loc, rot_z = compute_hb5_fixture_transform(fx, lvl.elevation, cx, cy)
    cab.obj.location = loc
    cab.obj.rotation_euler = (0.0, 0.0, rot_z)
    cab.obj["ESTISKETCH_ID"] = fx.identifier
    cab.obj["ESTISKETCH_SYMBOL"] = sym
    _move_hierarchy_to_collection(cab.obj, target_col)
    return cab.obj


def _build_countertop_mesh(
    fx: ParsedFixture,
    lvl: ParsedLevel,
    cx: float,
    cy: float,
    target_col,
):
    import bmesh

    if not fx.has_countertop:
        return None

    w_m = max(0.1, fx.width * INCH_TO_M)
    d_m = max(0.1, fx.depth * INCH_TO_M)
    hw, hd = w_m / 2.0, d_m / 2.0
    oh_m = max(0.0, fx.countertop_overhang * INCH_TO_M)
    ct_t = max(0.015, fx.countertop_thickness * INCH_TO_M)

    ct_presets = {
        "quartz": ((0.90, 0.90, 0.88, 1.0), 0.20),
        "granite": ((0.35, 0.36, 0.38, 1.0), 0.25),
        "marble": ((0.94, 0.94, 0.95, 1.0), 0.18),
        "butcher_block": ((0.64, 0.45, 0.26, 1.0), 0.45),
        "laminate": ((0.85, 0.82, 0.76, 1.0), 0.40),
        "concrete": ((0.55, 0.56, 0.56, 1.0), 0.65),
        "solid_surface": ((0.92, 0.92, 0.90, 1.0), 0.25),
    }
    col, rough = ct_presets.get(fx.countertop_material, ((0.88, 0.88, 0.86, 1.0), 0.25))
    if fx.countertop_color is not None:
        col = (fx.countertop_color[0], fx.countertop_color[1], fx.countertop_color[2], 1.0)

    ct_mat = _get_or_create_simple_material(
        f"EstiSketch_CT_{fx.countertop_material}", col, metallic=0.0, roughness=rough
    )
    steel_mat = _get_or_create_simple_material(
        "EstiSketch_BrushedSteel", (0.72, 0.74, 0.76, 1.0), metallic=0.85, roughness=0.25
    )

    bm = bmesh.new()
    if fx.symbol_type == "corner_base_cabinet":
        arm_m = min(24.0 * INCH_TO_M + oh_m, w_m, d_m)
        # Back at +Y (+hd) and Left (-hw); open quadrant at (+X, -Y)
        pts = [
            (-hw, hd),
            (hw, hd),
            (hw, hd - arm_m),
            (-hw + arm_m, hd - arm_m),
            (-hw + arm_m, -hd),
            (-hw, -hd),
        ]
        _extrude_prism_z(bm, pts, 0.0, ct_t)
        if fx.has_backsplash:
            bs_h = 4.0 * INCH_TO_M
            bs_d = 0.75 * INCH_TO_M
            _bm_add_box(bm, -hw, hd - bs_d, ct_t, hw, hd, ct_t + bs_h, mat_index=0)
            _bm_add_box(bm, -hw, -hd, ct_t, -hw + bs_d, hd - bs_d, ct_t + bs_h, mat_index=0)
    else:
        # Back at +hd, front overhangs toward -Y (-hd - oh_m)
        _bm_add_box(bm, -hw, -hd - oh_m, 0.0, hw, hd, ct_t, mat_index=0)
        if fx.has_backsplash and fx.symbol_type != "island_cabinet":
            bs_h = 4.0 * INCH_TO_M
            bs_d = 0.75 * INCH_TO_M
            _bm_add_box(bm, -hw, hd - bs_d, ct_t, hw, hd, ct_t + bs_h, mat_index=0)

    # Add integrated sink rim & faucet for sink base and bath vanities
    if fx.symbol_type in ("sink_base_cabinet", "vanity_single", "vanity_double"):
        bowls = [-w_m * 0.24, w_m * 0.24] if fx.symbol_type == "vanity_double" else [0.0]
        bw = min(w_m * 0.36, 18.0 * INCH_TO_M) if len(bowls) > 1 else min(w_m * 0.72, 28.0 * INCH_TO_M)
        bd = min(d_m * 0.62, 15.0 * INCH_TO_M)
        rim = 1.0 * INCH_TO_M
        for bx in bowls:
            _bm_add_box(bm, bx - bw / 2.0, -bd / 2.0, ct_t, bx + bw / 2.0, bd / 2.0, ct_t + 0.008, mat_index=1)
            _bm_add_box(bm, bx - bw / 2.0 + rim, -bd / 2.0 + rim, ct_t + 0.004, bx + bw / 2.0 - rim, bd / 2.0 - rim, ct_t + 0.012, mat_index=1)
            fy = bd / 2.0 + 0.025
            _bm_add_cylinder(bm, bx, fy, ct_t, ct_t + 0.16, 0.014, segments=12, mat_index=1)
            _bm_add_box(bm, bx - 0.012, fy - 0.09, ct_t + 0.14, bx + 0.012, fy + 0.01, ct_t + 0.165, mat_index=1)

    loc, rot_z = compute_centered_fixture_transform(fx, lvl.elevation + fx.height, cx, cy)
    obj = _finalize_bmesh_object(
        bm,
        f"Countertop_{fx.symbol_type}_{fx.identifier}",
        [ct_mat, steel_mat],
        loc,
        rot_z,
        target_col,
        fx.identifier,
    )
    obj["IS_COUNTERTOP_BP"] = True
    return obj


def _build_hb5_appliance(
    fx: ParsedFixture,
    lvl: ParsedLevel,
    cx: float,
    cy: float,
    target_col,
    types_appliances,
    appliance_geo,
):
    import bmesh
    import bpy

    cls_map = {
        "range_stove": ("Range", types_appliances.Range),
        "refrigerator": ("Refrigerator", types_appliances.Refrigerator),
        "dishwasher": ("Dishwasher", types_appliances.Dishwasher),
        "range_hood": ("Hood", types_appliances.Hood),
        "microwave": ("Microwave", types_appliances.Microwave),
        "cooktop": ("Cooktop", types_appliances.Cooktop),
        "wall_oven": ("Wall Oven", types_appliances.WallOven),
        "kitchen_sink_single": ("Sink", types_appliances.Sink),
        "kitchen_sink_double": ("Sink", types_appliances.Sink),
        "washer": ("Washing Machine", types_appliances.WashingMachine),
        "dryer": ("Dryer", types_appliances.Dryer),
    }
    label, app_cls = cls_map[fx.symbol_type]
    w_m = max(0.15, fx.width * INCH_TO_M)
    d_m = max(0.15, fx.depth * INCH_TO_M)
    h_m = max(0.08, fx.height * INCH_TO_M)

    app = app_cls()
    app.width = w_m
    app.depth = d_m
    app.height = h_m
    app.create(f"{label}_{fx.identifier}")
    app.set_input("Dim X", w_m)
    app.set_input("Dim Y", d_m)
    app.set_input("Dim Z", h_m)

    if fx.symbol_type == "kitchen_sink_single":
        app.obj["Sink Type"] = "Single Bowl"
    elif fx.symbol_type == "microwave" and fx.elevation >= 48.0:
        app.obj["Over Range"] = True

    if appliance_geo.supports(app.obj):
        try:
            opts = appliance_geo.defaults_for(app.obj)
            appliance_geo.set_opts(app.obj, opts)
            appliance_geo.build_geometry(app.obj)
        except Exception as exc:
            print(f"Warning: appliance_geo failed for {fx.identifier}: {exc}")
    else:
        # WashingMachine & Dryer solid cabinet + front porthole door in HB5 local coords (X: 0..W, Y: -D..0)
        white_mat = _get_or_create_simple_material(
            "EstiSketch_Appliance_White", (0.92, 0.93, 0.94, 1.0), metallic=0.1, roughness=0.35
        )
        dark_mat = _get_or_create_simple_material(
            "EstiSketch_Appliance_DarkGlass", (0.10, 0.11, 0.13, 1.0), metallic=0.4, roughness=0.18
        )
        bm = bmesh.new()
        _bm_add_box(bm, 0.0, -d_m, 0.0, w_m, 0.0, h_m, mat_index=0)
        _bm_add_box(bm, 0.02, -d_m - 0.015, h_m - 0.16, w_m - 0.02, -d_m, h_m - 0.02, mat_index=1)
        door_r = min(w_m, h_m) * 0.28
        _bm_add_box(
            bm,
            w_m / 2.0 - door_r,
            -d_m - 0.025,
            h_m * 0.46 - door_r,
            w_m / 2.0 + door_r,
            -d_m,
            h_m * 0.46 + door_r,
            mat_index=1,
        )
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
        body_mesh = bpy.data.meshes.new(f"{label}_Body_{fx.identifier}")
        bm.to_mesh(body_mesh)
        bm.free()
        body_mesh.materials.append(white_mat)
        body_mesh.materials.append(dark_mat)
        body_obj = bpy.data.objects.new(f"{label}_Body_{fx.identifier}", body_mesh)
        body_obj.parent = app.obj
        target_col.objects.link(body_obj)

    loc, rot_z = compute_hb5_fixture_transform(fx, lvl.elevation, cx, cy)
    app.obj.location = loc
    app.obj.rotation_euler = (0.0, 0.0, rot_z)
    app.obj["ESTISKETCH_ID"] = fx.identifier
    app.obj["ESTISKETCH_SYMBOL"] = fx.symbol_type
    _move_hierarchy_to_collection(app.obj, target_col)
    return app.obj


def _build_plumbing_mechanical_mesh(
    fx: ParsedFixture,
    lvl: ParsedLevel,
    cx: float,
    cy: float,
    target_col,
):
    import bmesh

    sym = fx.symbol_type
    w_m = max(0.15, fx.width * INCH_TO_M)
    d_m = max(0.15, fx.depth * INCH_TO_M)
    h_m = max(0.15, fx.height * INCH_TO_M)
    hw, hd = w_m / 2.0, d_m / 2.0

    porcelain = _get_or_create_simple_material(
        "EstiSketch_Porcelain", (0.96, 0.96, 0.97, 1.0), metallic=0.0, roughness=0.22
    )
    chrome = _get_or_create_simple_material(
        "EstiSketch_Chrome", (0.82, 0.84, 0.86, 1.0), metallic=0.92, roughness=0.15
    )
    glass = _get_or_create_simple_material(
        "EstiSketch_ShowerGlass", (0.78, 0.88, 0.92, 1.0), metallic=0.0, roughness=0.08, alpha=0.32
    )
    mech = _get_or_create_simple_material(
        "EstiSketch_MechanicalMetal", (0.52, 0.55, 0.58, 1.0), metallic=0.55, roughness=0.45
    )

    bm = bmesh.new()
    mats = [porcelain, chrome]

    if sym == "toilet":
        tank_d = d_m * 0.30
        _bm_add_box(bm, -hw * 0.88, hd - tank_d, h_m * 0.48, hw * 0.88, hd - 0.01, h_m, mat_index=0)
        _bm_add_box(bm, -hw * 0.92, hd - tank_d - 0.01, h_m - 0.04, hw * 0.92, hd, h_m + 0.02, mat_index=0)
        bowl_r = min(hw * 0.72, (d_m - tank_d) * 0.45)
        bowl_cy = -hd + bowl_r + 0.02
        _bm_add_cylinder(bm, 0.0, bowl_cy, 0.0, h_m * 0.52, bowl_r * 0.70, segments=18, mat_index=0)
        _bm_add_cylinder(bm, 0.0, bowl_cy, h_m * 0.46, h_m * 0.56, bowl_r, segments=20, mat_index=0)
    elif sym == "bathtub":
        wall_t = 2.5 * INCH_TO_M
        _bm_add_box(bm, -hw, -hd, 0.0, hw, hd, wall_t, mat_index=0)
        _bm_add_box(bm, -hw, hd - wall_t, wall_t, hw, hd, h_m, mat_index=0)
        _bm_add_box(bm, -hw, -hd, wall_t, hw, -hd + wall_t, h_m, mat_index=0)
        _bm_add_box(bm, -hw, -hd + wall_t, wall_t, -hw + wall_t, hd - wall_t, h_m, mat_index=0)
        _bm_add_box(bm, hw - wall_t, -hd + wall_t, wall_t, hw, hd - wall_t, h_m, mat_index=0)
        _bm_add_box(bm, -hw + 0.01, -0.02, h_m, -hw + 0.14, 0.02, h_m + 0.06, mat_index=1)
    elif sym in ("shower_square", "shower_corner"):
        mats = [porcelain, glass, chrome]
        curb_h = 4.0 * INCH_TO_M
        curb_w = 2.5 * INCH_TO_M
        gt = 0.4 * INCH_TO_M
        if sym == "shower_corner":
            chamf = min(w_m, d_m) * 0.42
            # Back at +Y (+hd) and Left (-hw), front-right chamfered corner at (+hw, -hd)
            pts = [(-hw, hd), (hw, hd), (hw, -hd + chamf), (hw - chamf, -hd), (-hw, -hd)]
            _extrude_prism_z(bm, pts, 0.0, curb_h)
            _bm_add_box(bm, hw - gt, -hd + chamf, curb_h, hw, hd, h_m, mat_index=1)
            _bm_add_box(bm, -hw, -hd, curb_h, hw - chamf, -hd + gt, h_m, mat_index=1)
            # Angled front glass panel
            x0, y0 = hw - chamf, -hd
            x1, y1 = hw, -hd + chamf
            dx, dy = x1 - x0, y1 - y0
            L = math.hypot(dx, dy) or 1.0
            nx, ny = -dy / L * gt, dx / L * gt
            _extrude_prism_z(bm, [(x0, y0), (x1, y1), (x1 + nx, y1 + ny), (x0 + nx, y0 + ny)], curb_h, h_m)
        else:
            _bm_add_box(bm, -hw, -hd, 0.0, hw, hd, curb_h, mat_index=0)
            _bm_add_box(bm, -hw, -hd, curb_h, hw, -hd + gt, h_m, mat_index=1)
            _bm_add_box(bm, hw - gt, -hd, curb_h, hw, hd, h_m, mat_index=1)
            _bm_add_box(bm, -hw, -hd, curb_h, -hw + gt, hd, h_m, mat_index=1)
        _bm_add_cylinder(bm, 0.0, hd - curb_w, h_m * 0.85, h_m * 0.88, 0.04, segments=12, mat_index=2)
    elif sym in ("pedestal_sink", "utility_sink"):
        basin_z0 = h_m - 0.16
        if sym == "pedestal_sink":
            _bm_add_cylinder(bm, 0.0, 0.02, 0.0, basin_z0, min(hw, hd) * 0.36, segments=16, mat_index=0)
        else:
            leg_w = 0.04
            for lx in (-hw + 0.03, hw - 0.07):
                for ly in (-hd + 0.03, hd - 0.07):
                    _bm_add_box(bm, lx, ly, 0.0, lx + leg_w, ly + leg_w, basin_z0, mat_index=1)
        _bm_add_box(bm, -hw, -hd, basin_z0, hw, hd, h_m, mat_index=0)
        _bm_add_cylinder(bm, 0.0, hd - 0.05, h_m, h_m + 0.14, 0.015, segments=10, mat_index=1)
    elif sym == "water_heater":
        mats = [mech, chrome]
        r = min(hw, hd) * 0.92
        _bm_add_cylinder(bm, 0.0, 0.0, 0.0, h_m, r, segments=24, mat_index=0)
        _bm_add_cylinder(bm, 0.0, 0.0, h_m, h_m + 0.15, r * 0.25, segments=14, mat_index=1)
    else:
        # furnace / air_conditioner
        mats = [mech, chrome]
        _bm_add_box(bm, -hw, -hd, 0.0, hw, hd, h_m, mat_index=0)
        if sym == "air_conditioner":
            _bm_add_cylinder(bm, 0.0, 0.0, h_m, h_m + 0.03, min(hw, hd) * 0.72, segments=20, mat_index=1)
        else:
            _bm_add_box(bm, -hw * 0.75, -hd - 0.01, h_m * 0.2, hw * 0.75, -hd, h_m * 0.8, mat_index=1)

    loc, rot_z = compute_centered_fixture_transform(fx, lvl.elevation, cx, cy)
    obj = _finalize_bmesh_object(
        bm,
        f"Plumbing_{sym}_{fx.identifier}",
        mats,
        loc,
        rot_z,
        target_col,
        fx.identifier,
    )
    obj["IS_PLUMBING_MECHANICAL"] = True
    return obj


def _build_furniture_mesh(
    fx: ParsedFixture,
    lvl: ParsedLevel,
    cx: float,
    cy: float,
    target_col,
):
    import bmesh

    sym = fx.symbol_type
    w_m = max(0.15, fx.width * INCH_TO_M)
    d_m = max(0.15, fx.depth * INCH_TO_M)
    h_m = max(0.15, fx.height * INCH_TO_M)
    hw, hd = w_m / 2.0, d_m / 2.0

    wood_mat = _get_or_create_simple_material(
        "EstiSketch_Furn_Wood", (0.45, 0.30, 0.18, 1.0), roughness=0.45
    )
    walnut_mat = _get_or_create_simple_material(
        "EstiSketch_Furn_Walnut", (0.26, 0.17, 0.11, 1.0), roughness=0.40
    )
    fabric_mat = _get_or_create_simple_material(
        "EstiSketch_Furn_Fabric", (0.58, 0.56, 0.52, 1.0), roughness=0.85
    )
    linen_mat = _get_or_create_simple_material(
        "EstiSketch_Furn_Linen", (0.90, 0.89, 0.86, 1.0), roughness=0.80
    )
    duvet_mat = _get_or_create_simple_material(
        "EstiSketch_Furn_Duvet", (0.34, 0.44, 0.54, 1.0), roughness=0.82
    )
    screen_mat = _get_or_create_simple_material(
        "EstiSketch_TVScreen", (0.04, 0.04, 0.05, 1.0), metallic=0.2, roughness=0.12
    )
    metal_mat = _get_or_create_simple_material(
        "EstiSketch_Furn_Metal", (0.22, 0.23, 0.25, 1.0), metallic=0.8, roughness=0.35
    )

    bm = bmesh.new()
    mats = [wood_mat]

    if sym in ("bed_king", "bed_queen", "bed_twin"):
        mats = [wood_mat, linen_mat, duvet_mat]
        frame_h = 0.22
        matt_h = 0.24
        hb_h = 1.08
        hb_t = 0.09
        # Wood platform & tall headboard at +Y (+hd)
        _bm_add_box(bm, -hw, -hd, 0.06, hw, hd, frame_h, mat_index=0)
        _bm_add_box(bm, -hw, hd - hb_t, 0.0, hw, hd, hb_h, mat_index=0)
        for lx in (-hw + 0.04, hw - 0.12):
            _bm_add_box(bm, lx, -hd + 0.04, 0.0, lx + 0.08, -hd + 0.12, 0.06, mat_index=0)
        # Mattress
        pad = 0.03
        _bm_add_box(bm, -hw + pad, -hd + pad, frame_h, hw - pad, hd - hb_t, frame_h + matt_h, mat_index=1)
        # Duvet covering lower 68% of mattress
        duvet_y = hd - hb_t - (d_m - hb_t) * 0.32
        _bm_add_box(
            bm,
            -hw + pad * 0.5,
            -hd + pad * 0.5,
            frame_h + matt_h * 0.5,
            hw - pad * 0.5,
            duvet_y,
            frame_h + matt_h + 0.03,
            mat_index=2,
        )
        # Pillows near headboard
        p_cnt = 1 if sym == "bed_twin" else 2
        p_gap = 0.08
        p_w = (w_m - (p_cnt + 1) * p_gap) / p_cnt
        for pi in range(p_cnt):
            px0 = -hw + p_gap + pi * (p_w + p_gap)
            _bm_add_box(
                bm,
                px0,
                hd - hb_t - 0.36,
                frame_h + matt_h,
                px0 + p_w,
                hd - hb_t - 0.04,
                frame_h + matt_h + 0.11,
                mat_index=1,
            )

    elif sym in ("sofa", "loveseat", "armchair"):
        mats = [fabric_mat, walnut_mat]
        leg_h = 0.10
        base_h = 0.24
        seat_h = 0.44
        arm_w = 0.15
        back_d = 0.20
        # Legs
        for lx in (-hw + 0.04, hw - 0.10):
            for ly in (-hd + 0.04, hd - 0.10):
                _bm_add_box(bm, lx, ly, 0.0, lx + 0.06, ly + 0.06, leg_h, mat_index=1)
        # Frame base, backrest (+Y), left/right arms
        _bm_add_box(bm, -hw, -hd, leg_h, hw, hd, base_h, mat_index=0)
        _bm_add_box(bm, -hw, hd - back_d, base_h, hw, hd, h_m, mat_index=0)
        _bm_add_box(bm, -hw, -hd, base_h, -hw + arm_w, hd - back_d, h_m * 0.72, mat_index=0)
        _bm_add_box(bm, hw - arm_w, -hd, base_h, hw, hd - back_d, h_m * 0.72, mat_index=0)
        # Seat cushions
        c_cnt = 3 if sym == "sofa" else (2 if sym == "loveseat" else 1)
        c_span = max(0.2, w_m - 2.0 * arm_w)
        c_w = (c_span - (c_cnt - 1) * 0.015) / c_cnt
        for ci in range(c_cnt):
            cx0 = -hw + arm_w + ci * (c_w + 0.015)
            _bm_add_box(bm, cx0, -hd + 0.01, base_h, cx0 + c_w, hd - back_d - 0.01, seat_h, mat_index=0)

    elif sym in ("dining_table", "coffee_table", "end_table"):
        mats = [wood_mat]
        top_t = 0.045
        leg_w = 0.065 if sym == "dining_table" else 0.05
        inset = 0.05
        _bm_add_box(bm, -hw, -hd, h_m - top_t, hw, hd, h_m, mat_index=0)
        # Apron
        _bm_add_box(bm, -hw + inset, -hd + inset, h_m - top_t - 0.06, hw - inset, hd - inset, h_m - top_t, mat_index=0)
        for lx in (-hw + inset, hw - inset - leg_w):
            for ly in (-hd + inset, hd - inset - leg_w):
                _bm_add_box(bm, lx, ly, 0.0, lx + leg_w, ly + leg_w, h_m - top_t, mat_index=0)

    elif sym == "dining_chair":
        mats = [wood_mat, fabric_mat]
        seat_z = 0.45
        leg_w = 0.038
        for lx in (-hw + 0.02, hw - 0.02 - leg_w):
            for ly in (-hd + 0.02, hd - 0.02 - leg_w):
                _bm_add_box(bm, lx, ly, 0.0, lx + leg_w, ly + leg_w, seat_z, mat_index=0)
        _bm_add_box(bm, -hw, -hd, seat_z, hw, hd, seat_z + 0.05, mat_index=1)
        _bm_add_box(bm, -hw + 0.02, hd - 0.05, seat_z + 0.05, hw - 0.02, hd, h_m, mat_index=0)

    elif sym == "office_chair":
        mats = [metal_mat, fabric_mat]
        seat_z = 0.46
        _bm_add_cylinder(bm, 0.0, 0.0, 0.0, 0.06, 0.04, segments=12, mat_index=0)
        _bm_add_box(bm, -hw * 0.8, -0.025, 0.02, hw * 0.8, 0.025, 0.05, mat_index=0)
        _bm_add_box(bm, -0.025, -hd * 0.8, 0.02, 0.025, hd * 0.8, 0.05, mat_index=0)
        _bm_add_cylinder(bm, 0.0, 0.0, 0.05, seat_z, 0.03, segments=12, mat_index=0)
        _bm_add_box(bm, -hw * 0.85, -hd * 0.82, seat_z, hw * 0.85, hd * 0.82, seat_z + 0.07, mat_index=1)
        _bm_add_box(bm, -hw * 0.78, hd * 0.70, seat_z + 0.07, hw * 0.78, hd * 0.86, h_m, mat_index=1)
        _bm_add_box(bm, -hw * 0.92, -hd * 0.35, seat_z + 0.07, -hw * 0.80, hd * 0.65, seat_z + 0.24, mat_index=0)
        _bm_add_box(bm, hw * 0.80, -hd * 0.35, seat_z + 0.07, hw * 0.92, hd * 0.65, seat_z + 0.24, mat_index=0)

    elif sym == "desk":
        mats = [walnut_mat, metal_mat]
        top_t = 0.04
        ped_w = min(0.40, w_m * 0.28)
        _bm_add_box(bm, -hw, -hd, h_m - top_t, hw, hd, h_m, mat_index=0)
        _bm_add_box(bm, hw - ped_w - 0.02, -hd + 0.03, 0.05, hw - 0.02, hd - 0.03, h_m - top_t, mat_index=0)
        _bm_add_box(bm, -hw + 0.03, -hd + 0.04, 0.0, -hw + 0.08, hd - 0.04, h_m - top_t, mat_index=1)

    elif sym in ("nightstand", "dresser", "tv_console"):
        mats = [walnut_mat, metal_mat, screen_mat]
        _bm_add_box(bm, -hw, -hd, 0.06, hw, hd, h_m, mat_index=0)
        for lx in (-hw + 0.04, hw - 0.09):
            for ly in (-hd + 0.04, hd - 0.09):
                _bm_add_box(bm, lx, ly, 0.0, lx + 0.05, ly + 0.05, 0.06, mat_index=0)
        rows = 2 if sym == "nightstand" else (3 if sym == "dresser" else 2)
        band_h = (h_m - 0.12) / rows
        for ri in range(rows):
            bz = 0.08 + ri * band_h
            _bm_add_box(bm, -hw + 0.04, -hd - 0.015, bz + 0.015, hw - 0.04, -hd, bz + band_h - 0.015, mat_index=0)
            _bm_add_box(bm, -0.06, -hd - 0.025, bz + band_h * 0.45, 0.06, -hd - 0.015, bz + band_h * 0.55, mat_index=1)
        if sym == "tv_console":
            tv_w = min(w_m * 0.82, 1.32)
            tv_h = 0.76
            _bm_add_box(bm, -0.18, -0.06, h_m, 0.18, 0.06, h_m + 0.03, mat_index=1)
            _bm_add_box(bm, -0.04, -0.02, h_m + 0.03, 0.04, 0.02, h_m + 0.12, mat_index=1)
            _bm_add_box(bm, -tv_w / 2.0, -0.03, h_m + 0.10, tv_w / 2.0, 0.03, h_m + 0.10 + tv_h, mat_index=2)

    elif sym == "bookshelf":
        mats = [wood_mat]
        bt = 0.03
        _bm_add_box(bm, -hw, -hd, 0.0, -hw + bt, hd, h_m, mat_index=0)
        _bm_add_box(bm, hw - bt, -hd, 0.0, hw, hd, h_m, mat_index=0)
        _bm_add_box(bm, -hw + bt, hd - bt, 0.0, hw - bt, hd, h_m, mat_index=0)
        for si in range(6):
            sz = (si / 5.0) * (h_m - bt)
            _bm_add_box(bm, -hw + bt, -hd, sz, hw - bt, hd - bt, sz + bt, mat_index=0)

    loc, rot_z = compute_centered_fixture_transform(fx, lvl.elevation, cx, cy)
    obj = _finalize_bmesh_object(
        bm,
        f"Furniture_{sym}_{fx.identifier}",
        mats,
        loc,
        rot_z,
        target_col,
        fx.identifier,
    )
    obj["IS_FURNITURE"] = True
    return obj


def _add_boolean_cut(wall_obj, cutting_obj) -> None:
    mod_name = f"Boolean_{cutting_obj.name}"
    if mod_name in wall_obj.modifiers:
        return
    mod = wall_obj.modifiers.new(name=mod_name, type="BOOLEAN")
    mod.operation = "DIFFERENCE"
    mod.object = cutting_obj
    mod.solver = "EXACT"
    cutting_obj.hide_render = True


def _build_wall_span_cutter(
    wall_obj,
    x_start_m: float,
    x_end_m: float,
    wall_len_m: float,
    thickness_m: float,
    z_min_m: float,
    z_max_m: float,
    openings_col,
    name: str,
):
    import bmesh
    import bpy

    x0 = x_start_m - (0.005 if x_start_m <= 1e-4 else 0.0)
    x1 = x_end_m + (0.005 if x_end_m >= wall_len_m - 1e-4 else 0.0)
    bm = bmesh.new()
    _bm_add_box(bm, x0, -0.02, z_min_m - 0.01, x1, thickness_m + 0.02, z_max_m)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    mesh = bpy.data.meshes.new(name)
    bm.to_mesh(mesh)
    bm.free()
    cutter_obj = bpy.data.objects.new(name, mesh)
    cutter_obj.parent = wall_obj
    cutter_obj.display_type = "WIRE"
    cutter_obj.hide_viewport = True
    cutter_obj.hide_render = True
    openings_col.objects.link(cutter_obj)
    return cutter_obj


def _map_window_type(win_type: str) -> str:
    if "fixed" in win_type or "picture" in win_type:
        return "PICTURE"
    if "casement" in win_type:
        return "CASEMENT"
    if "awning" in win_type:
        return "AWNING"
    if "hung" in win_type:
        return "HUNG"
    return "SLIDER"


def _tag_corner_origin_fixture(obj, fx: ParsedFixture) -> None:
    """Record the object-local offset from the HB5 back-left origin to the fixture center.

    EstiSketch fixtures are center-positioned, so the Blender-to-EstiSketch sync needs this
    offset (meters, object-local) to convert an edited Blender pose back to a fixture center.
    """
    obj["ESTISKETCH_CENTER_OFFSET"] = [
        fx.width * INCH_TO_M / 2.0,
        -fx.depth * INCH_TO_M / 2.0,
    ]


def _has_solid_geometry(root_obj, depsgraph) -> bool:
    """True if ``root_obj`` or any descendant is a visible, solid-shaded mesh with faces."""
    for obj in [root_obj, *root_obj.children_recursive]:
        if obj.type != "MESH" or obj.display_type in ("WIRE", "BOUNDS"):
            continue
        if obj.hide_viewport or obj.hide_get():
            continue
        try:
            evaluated = obj.evaluated_get(depsgraph)
            mesh = evaluated.to_mesh()
            n_faces = len(mesh.polygons)
            evaluated.to_mesh_clear()
        except RuntimeError:
            continue
        if n_faces > 0:
            return True
    return False


def _ensure_solid_fixtures(fixtures: List[ParsedFixture]) -> int:
    """Give every fixture that would otherwise show only as a wire cage a solid placeholder.

    Returns the number of placeholders added. Placeholders are solid boxes matching the
    fixture ``(width, depth, height)`` so no EstiSketch item is ever missing or wireframe-only.
    """
    import bmesh
    import bpy

    by_id = {fx.identifier: fx for fx in fixtures}
    depsgraph = bpy.context.evaluated_depsgraph_get()
    mat = _get_or_create_simple_material(
        "EstiSketch_Placeholder", (0.72, 0.72, 0.74, 1.0), roughness=0.6
    )
    added = 0
    for obj in list(bpy.data.objects):
        fid = obj.get("ESTISKETCH_ID")
        fx = by_id.get(str(fid)) if fid else None
        if fx is None or obj.parent is not None or _has_solid_geometry(obj, depsgraph):
            continue
        w_m = max(0.05, fx.width * INCH_TO_M)
        d_m = max(0.05, fx.depth * INCH_TO_M)
        h_m = max(0.05, fx.height * INCH_TO_M)
        offset = obj.get("ESTISKETCH_CENTER_OFFSET")
        cx, cy = (float(offset[0]), float(offset[1])) if offset else (0.0, 0.0)
        bm = bmesh.new()
        _bm_add_box(bm, cx - w_m / 2, cy - d_m / 2, 0.0, cx + w_m / 2, cy + d_m / 2, h_m, 0)
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
        mesh = bpy.data.meshes.new(f"Placeholder_{fx.identifier}")
        bm.to_mesh(mesh)
        bm.free()
        mesh.materials.append(mat)
        ph = bpy.data.objects.new(f"Placeholder_{fx.symbol_type}_{fx.identifier}", mesh)
        ph.parent = obj
        for col in obj.users_collection:
            col.objects.link(ph)
        print(f"Warning: added solid placeholder for {fx.symbol_type} {fx.identifier}")
        added += 1
    return added


def _load_live_sync_module():
    """Load ``blender_live_sync.py`` by path (it only needs ``bpy`` + stdlib)."""
    import importlib.util

    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "blender_live_sync.py")
    spec = importlib.util.spec_from_file_location("estisketch_blender_live_sync", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _schedule_viewport_frame() -> None:
    import bpy

    def _frame_once():
        for window in bpy.context.window_manager.windows:
            for area in window.screen.areas:
                if area.type != "VIEW_3D":
                    continue
                for space in area.spaces:
                    if space.type == "VIEW_3D":
                        space.shading.color_type = "OBJECT"
                region = next((r for r in area.regions if r.type == "WINDOW"), None)
                if region is not None:
                    with bpy.context.temp_override(window=window, area=area, region=region):
                        try:
                            bpy.ops.view3d.view_all(center=False)
                        except Exception:
                            pass
        return None

    bpy.app.timers.register(_frame_once, first_interval=0.1)


def build_in_blender(
    xml_path: str,
    save_blend_path: str = "",
    sync_dir: str = "",
    custom_assets_json: str = "",
) -> Dict[str, int]:
    """Build an EstiSketch XML project inside the active Blender scene using HB5.

    Args:
        xml_path: EstiSketch project XML.
        save_blend_path: Optional ``.blend`` path to save after building.
        sync_dir: If set, enables automatic send-back: custom assets are imported, the scene is
            saved as ``model.blend`` there, and every Ctrl+S writes ``delta.esk-delta.zip``.
        custom_assets_json: ``custom_assets.json`` produced by the EstiSketch launcher.
    """
    import importlib
    import bpy

    pkg_name = find_hb5_package()
    hb_types = importlib.import_module(pkg_name + ".hb_types")
    walls_op = importlib.import_module(pkg_name + ".operators.walls")
    door_window_geo = importlib.import_module(
        pkg_name + ".product_libraries.common.door_window_geo"
    )
    hb_details = importlib.import_module(pkg_name + ".hb_details")
    GeoNodeText = hb_details.GeoNodeText
    ops_stairs = importlib.import_module(pkg_name + ".operators.ops_stairs")
    types_frameless = importlib.import_module(
        pkg_name + ".product_libraries.frameless.types_frameless"
    )
    solver_frameless = importlib.import_module(
        pkg_name + ".product_libraries.frameless.solver_frameless"
    )
    types_appliances = importlib.import_module(
        pkg_name + ".product_libraries.common.types_appliances"
    )
    appliance_geo = importlib.import_module(
        pkg_name + ".product_libraries.common.appliance_geo"
    )
    surface_materials = importlib.import_module(pkg_name + ".surface_materials")

    project = parse_estisketch_xml(xml_path)
    if project.skipped_openings:
        print(
            f"Warning: skipped {len(project.skipped_openings)} orphaned opening(s): "
            + ", ".join(project.skipped_openings[:8])
        )
    orient_interior_wall_chains(project)
    cx, cy = compute_plan_center(project)

    scene = bpy.context.scene
    _clear_default_scene(scene)

    scene["IS_ROOM_SCENE"] = True
    scene.unit_settings.system = "IMPERIAL"
    scene.unit_settings.length_unit = "INCHES"

    root_col = _ensure_collection("EstiSketch Import", scene.collection)
    _ensure_sun_light(scene, root_col, north_angle=project.north_angle)
    foundations_col = _ensure_collection("Foundations", root_col)

    level_by_id = {lvl.id: lvl for lvl in project.levels}
    level_cols: Dict[str, Dict[str, object]] = {}
    for lvl in project.levels:
        lvl_col = _ensure_collection(f"EstiSketch - {lvl.name}", root_col)
        level_cols[lvl.id] = {
            "walls": _ensure_collection(f"{lvl.name} - Walls", lvl_col),
            "openings": _ensure_collection(f"{lvl.name} - Openings", lvl_col),
            "trim": _ensure_collection(f"{lvl.name} - Trim", lvl_col),
            "rooms": _ensure_collection(f"{lvl.name} - Rooms", lvl_col),
            "ceilings": _ensure_collection(f"{lvl.name} - Ceilings", lvl_col),
            "roofs": _ensure_collection(f"{lvl.name} - Roofs", lvl_col),
            "stairs": _ensure_collection(f"{lvl.name} - Stairs", lvl_col),
            "cabinets": _ensure_collection(f"{lvl.name} - Cabinets & Appliances", lvl_col),
            "plumbing": _ensure_collection(f"{lvl.name} - Plumbing & Mechanical", lvl_col),
            "furniture": _ensure_collection(f"{lvl.name} - Furniture", lvl_col),
        }

    # Build walls grouped by set_index so sequential walls in a set connect cleanly
    # without closing a cyclic COPY_LOCATION dependency loop.
    wall_segments: Dict[Tuple[int, int], List[Tuple[object, float, float, ParsedWall]]] = {}
    built_wall_records: List[Tuple[ParsedWall, object, float, ParsedLevel]] = []
    miter_records_by_level: Dict[
        str, List[Tuple[object, Tuple[float, float], Tuple[float, float], float, bool]]
    ] = {}
    walls_by_set: Dict[int, List[ParsedWall]] = {}
    for pw in project.walls:
        walls_by_set.setdefault(pw.set_index, []).append(pw)

    wall_count = 0
    for set_idx, set_walls in walls_by_set.items():
        prev_hb_wall = None
        prev_end_m: Optional[Tuple[float, float]] = None

        for pw in set_walls:
            if pw.symbolic:
                continue
            lvl = level_by_id.get(pw.level_id, project.levels[0])
            z_m = lvl.elevation * INCH_TO_M
            walls_col = level_cols[lvl.id]["walls"]

            if pw.is_curved and pw.arc_center is not None and pw.arc_radius is not None:
                pts_in = tessellate_curved_wall_points(
                    pw.start, pw.end, pw.arc_center, pw.arc_radius
                )
            else:
                pts_in = [pw.start, pw.end]

            seg_count = len(pts_in) - 1
            segs_for_wall: List[Tuple[object, float, float, ParsedWall]] = []

            for seg_i in range(seg_count):
                p0 = inches_to_blender_xy(pts_in[seg_i][0], pts_in[seg_i][1], cx, cy)
                p1 = inches_to_blender_xy(pts_in[seg_i + 1][0], pts_in[seg_i + 1][1], cx, cy)
                dx = p1[0] - p0[0]
                dy = p1[1] - p0[1]
                length_m = math.hypot(dx, dy)
                if length_m < 1e-4:
                    continue

                t0 = seg_i / seg_count
                t1 = (seg_i + 1) / seg_count
                h0_m = (pw.height + (pw.height_at_end - pw.height) * t0) * INCH_TO_M
                h1_m = (pw.height + (pw.height_at_end - pw.height) * t1) * INCH_TO_M
                thick_m = max(0.02, pw.width * INCH_TO_M)

                hb_wall = hb_types.GeoNodeWall()
                suffix = f"_{seg_i}" if seg_count > 1 else ""
                hb_wall.create(f"Wall_{set_idx}_{pw.wall_index}{suffix}")
                hb_wall.obj["WALL_TYPE"] = "Exterior" if pw.exterior_wall else "Interior"
                hb_wall.obj["ESTISKETCH_ID"] = pw.identifier
                hb_wall.obj["ESTISKETCH_LEVEL"] = lvl.id

                hb_wall.obj.location = (p0[0], p0[1], z_m)
                hb_wall.obj.rotation_euler = (0.0, 0.0, math.atan2(dy, dx))
                hb_wall.set_input("Length", length_m)
                hb_wall.set_input("Thickness", thick_m)
                hb_wall.set_input("Height", h0_m)
                if hb_wall.has_input("End Height"):
                    hb_wall.set_input("End Height", h1_m)
                _assign_wall_materials(
                    hb_wall, scene, pw=pw, surface_materials=surface_materials
                )

                _move_object_to_collection(hb_wall.obj, walls_col)
                if hb_wall.obj_x is not None:
                    _move_object_to_collection(hb_wall.obj_x, walls_col)

                # Connect sequentially if this segment starts at the previous end.
                if (
                    prev_hb_wall is not None
                    and prev_end_m is not None
                    and math.hypot(p0[0] - prev_end_m[0], p0[1] - prev_end_m[1]) < 0.01
                ):
                    hb_wall.connect_to_wall(prev_hb_wall)

                prev_hb_wall = hb_wall
                prev_end_m = p1
                wall_count += 1
                seg_min_h = min(h0_m, h1_m)
                segs_for_wall.append((hb_wall, length_m, seg_min_h, pw))
                built_wall_records.append((pw, hb_wall, length_m, lvl))
                miter_records_by_level.setdefault(lvl.id, []).append(
                    (hb_wall, p0, p1, thick_m, pw.exterior_wall)
                )

            if segs_for_wall:
                wall_segments[(pw.set_index, pw.wall_index)] = segs_for_wall

    bpy.context.view_layer.update()
    if hasattr(walls_op, "refresh_wall_junctions"):
        walls_op.refresh_wall_junctions(scene)
    elif hasattr(walls_op, "update_all_wall_miters"):
        walls_op.update_all_wall_miters()

    for lvl_records in miter_records_by_level.values():
        entries = [
            (hb_w.obj.name, p0, p1, thick_m, is_ext)
            for hb_w, p0, p1, thick_m, is_ext in lvl_records
        ]
        miters = compute_level_wall_miters(entries)
        for hb_w, _, _, _, _ in lvl_records:
            la, ra = miters.get(hb_w.obj.name, (0.0, 0.0))
            hb_w.set_input("Left Angle", la)
            hb_w.set_input("Right Angle", ra)
            hb_w.obj.update_tag()
    bpy.context.view_layer.update()

    hb_props = scene.home_builder
    hb_wm_prefs = bpy.context.window_manager.home_builder.get_user_preferences(bpy.context)

    def _resolve_opening_host(set_idx: int, wall_idx: int, ratio: float):
        segs = wall_segments.get((set_idx, wall_idx))
        if not segs:
            return None
        if len(segs) == 1:
            return (*segs[0], ratio)
        seg_idx, local_r = resolve_curved_wall_segment([s[1] for s in segs], ratio)
        return (*segs[seg_idx], local_r)

    def _apply_neighbor_opening_cuts(
        cuts: List[WallOpeningCut],
        host_pw: ParsedWall,
        host_hb_wall,
        primary_cutter,
        z_min_m: float,
        z_max_m: float,
        openings_col,
        opening_tag: str,
    ) -> None:
        host_thick_m = host_hb_wall.get_input("Thickness")
        for cut in cuts:
            if cut.wall is host_pw:
                continue
            cut_segs = wall_segments.get((cut.wall.set_index, cut.wall.wall_index))
            if not cut_segs:
                continue
            nb_hb_wall, nb_len_m, _, _ = cut_segs[0]
            nb_thick_m = nb_hb_wall.get_input("Thickness")
            same_or_thinner = cut.same_direction and nb_thick_m <= host_thick_m + 1e-4
            if same_or_thinner and primary_cutter is not None:
                _add_boolean_cut(nb_hb_wall.obj, primary_cutter)
            else:
                extra_cutter = _build_wall_span_cutter(
                    nb_hb_wall.obj,
                    cut.x_start_m,
                    cut.x_end_m,
                    nb_len_m,
                    nb_thick_m,
                    z_min_m,
                    z_max_m,
                    openings_col,
                    f"{opening_tag}_Cut_{cut.wall.identifier}",
                )
                _add_boolean_cut(nb_hb_wall.obj, extra_cutter)

    door_intervals_by_wall_obj: Dict[int, List[Tuple[float, float]]] = {}
    door_count = 0
    for pd in project.doors:
        resolved = _resolve_opening_host(pd.set_index, pd.wall_index, pd.ratio)
        if resolved is None:
            continue
        hb_wall, wall_len_m, min_h_m, host_pw, local_ratio = resolved
        lvl = level_by_id.get(pd.level_id, project.levels[0])
        openings_col = level_cols[lvl.id]["openings"]

        if not host_pw.is_curved:
            placement = resolve_opening_chain_placement(
                host_pw, local_ratio, pd.width, project.walls
            )
            width_m = placement.width_m
            x_local = placement.x_local_m
            eff_min_h_m = placement.min_height_m
            cuts = placement.cuts
            for cut in cuts:
                cut_segs = wall_segments.get((cut.wall.set_index, cut.wall.wall_index))
                if cut_segs:
                    door_intervals_by_wall_obj.setdefault(
                        id(cut_segs[0][0].obj), []
                    ).append((cut.x_start_m, cut.x_end_m))
        else:
            width_m = max(0.1, min(pd.width * INCH_TO_M, wall_len_m))
            x_local = compute_opening_local_x(local_ratio, wall_len_m, width_m)
            eff_min_h_m = min_h_m
            cuts = []
            door_intervals_by_wall_obj.setdefault(id(hb_wall.obj), []).append(
                (x_local, x_local + width_m)
            )

        height_m = max(0.2, min(pd.height * INCH_TO_M, eff_min_h_m))
        thickness_m = hb_wall.get_input("Thickness")

        cage = hb_types.GeoNodeCage()
        cage.create(f"Door_{pd.identifier}")
        cage.obj["IS_ENTRY_DOOR_BP"] = True
        cage.obj["MENU_ID"] = "HOME_BUILDER_MT_door_commands"
        cage.obj["ESTISKETCH_ID"] = pd.identifier
        cage.set_input("Dim X", width_m)
        cage.set_input("Dim Y", thickness_m)
        cage.set_input("Dim Z", height_m)
        cage.obj.color = hb_wm_prefs.door_window_color
        cage.obj.display_type = "WIRE"

        cage.obj.parent = hb_wall.obj
        cage.obj.location = (x_local, 0.0, 0.0)
        cage.obj.rotation_euler = (0.0, 0.0, 0.0)
        _move_object_to_collection(cage.obj, openings_col)

        primary_cutter = None
        if pd.door_type == "frame":
            cage.obj["IS_OPEN_DOORWAY"] = True
            _add_boolean_cut(hb_wall.obj, cage.obj)
            primary_cutter = cage.obj
        elif pd.door_type == "garage":
            cage.obj["IS_GARAGE_DOOR"] = True
            _, primary_cutter = _build_garage_door_mesh(
                cage.obj, width_m, thickness_m, height_m, openings_col, hb_wall.obj
            )
        else:
            dim_x = cage.var_input("Dim X", "dim_x")
            dim_y = cage.var_input("Dim Y", "dim_y")
            dim_z = cage.var_input("Dim Z", "dim_z")
            is_double = (
                "double" in pd.door_type
                or "bi-fold" in pd.door_type
                or pd.door_type == "sliding"
            )

            swing_obj = hb_types.GeoNodeDoorSwing()
            swing_obj.create("Door Swing Annotation")
            swing_obj.obj.parent = cage.obj
            swing_obj.driver_input("Dim X", "dim_x", [dim_x])
            swing_obj.driver_input("Dim Y", "dim_y", [dim_y])
            swing_obj.set_input("Is Double", is_double)
            swing_obj.set_input("Swing Inside", pd.orientation == "inswing")
            swing_obj.set_input("Is Left", pd.swing == "left")
            _move_object_to_collection(swing_obj.obj, openings_col)

            txt = GeoNodeText()
            txt.create("Door Text", "DOOR", hb_props.annotation_text_size)
            txt.obj.parent = cage.obj
            txt.obj.rotation_euler.x = math.radians(90)
            txt.driver_location("x", "dim_x/2", [dim_x])
            txt.driver_location("y", "dim_y/2", [dim_y])
            txt.driver_location("z", "dim_z/2", [dim_z])
            txt.set_alignment("CENTER", "CENTER")
            _move_object_to_collection(txt.obj, openings_col)

            opts = dict(door_window_geo.DOOR_DEFAULTS)
            opts["style"] = "CUSTOM"
            opts["threshold_height"] = 0.75 * INCH_TO_M if host_pw.exterior_wall else 0.0
            if pd.door_type == "sliding":
                opts["door_style"] = "LITE_FULL"
                opts["glass_grid_cols"] = 2
                opts["glass_grid_rows"] = 1
            elif "double" in pd.door_type and "bi-fold" not in pd.door_type:
                if host_pw.exterior_wall:
                    opts["door_style"] = "LITE_FULL"
                    opts["glass_grid_cols"] = 2
                    opts["glass_grid_rows"] = 3
                else:
                    opts["door_style"] = "PANEL_4"
            elif "bi-fold" in pd.door_type:
                opts["door_style"] = "PANEL_2"
            elif "pocket" in pd.door_type:
                opts["door_style"] = "FLUSH"
            else:
                opts["door_style"] = "LITE_HALF" if host_pw.exterior_wall else "PANEL_6"

            door_window_geo.set_opts(cage.obj, opts)
            cutting_obj = door_window_geo.update_reveal_cutter(cage.obj)
            _add_boolean_cut(hb_wall.obj, cutting_obj)
            primary_cutter = cutting_obj
            door_window_geo.build_geometry(cage.obj)
            for child in cage.obj.children:
                _move_object_to_collection(child, openings_col)

        _apply_neighbor_opening_cuts(
            cuts,
            host_pw,
            hb_wall,
            primary_cutter,
            0.0,
            height_m,
            openings_col,
            f"Door_{pd.identifier}",
        )
        door_count += 1

    window_count = 0
    for pw_win in project.windows:
        resolved = _resolve_opening_host(pw_win.set_index, pw_win.wall_index, pw_win.ratio)
        if resolved is None:
            continue
        hb_wall, wall_len_m, min_h_m, host_pw, local_ratio = resolved
        lvl = level_by_id.get(pw_win.level_id, project.levels[0])
        openings_col = level_cols[lvl.id]["openings"]

        if not host_pw.is_curved:
            placement = resolve_opening_chain_placement(
                host_pw, local_ratio, pw_win.width, project.walls
            )
            width_m = placement.width_m
            x_local = placement.x_local_m
            eff_min_h_m = placement.min_height_m
            cuts = placement.cuts
        else:
            width_m = max(0.1, min(pw_win.width * INCH_TO_M, wall_len_m))
            x_local = compute_opening_local_x(local_ratio, wall_len_m, width_m)
            eff_min_h_m = min_h_m
            cuts = []

        height_m = max(0.1, min(pw_win.height * INCH_TO_M, max(0.1, eff_min_h_m - 0.05)))
        thickness_m = hb_wall.get_input("Thickness")
        z_local = compute_window_sill_height_m(height_m, eff_min_h_m)

        cage = hb_types.GeoNodeCage()
        cage.create(f"Window_{pw_win.identifier}")
        cage.obj["IS_WINDOW_BP"] = True
        cage.obj["MENU_ID"] = "HOME_BUILDER_MT_window_commands"
        cage.obj["ESTISKETCH_ID"] = pw_win.identifier
        cage.set_input("Dim X", width_m)
        cage.set_input("Dim Y", thickness_m)
        cage.set_input("Dim Z", height_m)
        cage.obj.color = hb_wm_prefs.door_window_color
        cage.obj.display_type = "WIRE"

        cage.obj.parent = hb_wall.obj
        cage.obj.location = (x_local, 0.0, z_local)
        cage.obj.rotation_euler = (0.0, 0.0, 0.0)
        _move_object_to_collection(cage.obj, openings_col)

        dim_x = cage.var_input("Dim X", "dim_x")
        dim_y = cage.var_input("Dim Y", "dim_y")
        dim_z = cage.var_input("Dim Z", "dim_z")
        txt = GeoNodeText()
        txt.create("Window Text", "WINDOW", hb_props.annotation_text_size)
        txt.obj.parent = cage.obj
        txt.obj.rotation_euler.x = math.radians(90)
        txt.driver_location("x", "dim_x/2", [dim_x])
        txt.driver_location("y", "dim_y/2", [dim_y])
        txt.driver_location("z", "dim_z/2", [dim_z])
        txt.set_alignment("CENTER", "CENTER")
        _move_object_to_collection(txt.obj, openings_col)

        opts = dict(door_window_geo.WINDOW_DEFAULTS)
        opts["style"] = "CUSTOM"
        opts["window_type"] = _map_window_type(pw_win.window_type)
        door_window_geo.set_opts(cage.obj, opts)
        cutting_obj = door_window_geo.update_reveal_cutter(cage.obj)
        _add_boolean_cut(hb_wall.obj, cutting_obj)
        door_window_geo.build_geometry(cage.obj)
        for child in cage.obj.children:
            _move_object_to_collection(child, openings_col)

        _apply_neighbor_opening_cuts(
            cuts,
            host_pw,
            hb_wall,
            cutting_obj,
            z_local,
            z_local + height_m,
            openings_col,
            f"Window_{pw_win.identifier}",
        )
        window_count += 1

    door_window_geo.hide_reveal_cutters()

    baseboard_count = 0
    for b_idx, (pw, hb_wall, seg_len_m, lvl) in enumerate(built_wall_records):
        bb_obj = _build_wall_baseboards(
            pw,
            hb_wall,
            seg_len_m,
            door_intervals_by_wall_obj.get(id(hb_wall.obj), []),
            level_cols[lvl.id]["trim"],
            f"Baseboard_{pw.identifier}_{b_idx}",
        )
        if bb_obj is not None:
            baseboard_count += 1

    footer_count = _build_level_footers(
        project, level_by_id, cx, cy, foundations_col, surface_materials
    )
    _build_level_rim_bands(
        project, level_by_id, level_cols, cx, cy, scene, surface_materials
    )

    room_cutouts = compute_room_hole_cutouts(project)
    room_count = 0
    ceiling_count = 0
    cutout_count = 0
    for idx, pr in enumerate(project.rooms):
        lvl = level_by_id.get(pr.level_id, project.levels[0])
        rooms_col = level_cols[lvl.id]["rooms"]
        ceilings_col = level_cols[lvl.id]["ceilings"]
        pts_m = [inches_to_blender_xy(x, y, cx, cy) for x, y in pr.points]
        if pr.is_slab:
            thick_m = max(0.01, pr.slab_thickness * INCH_TO_M)
        elif lvl.elevation > 0.1:
            thick_m = max(0.01, lvl.floor_thickness * INCH_TO_M)
        else:
            thick_m = 0.01
        z_top_m = lvl.elevation * INCH_TO_M
        floor_mat = _get_or_create_floor_material(pr, surface_materials)
        floor_obj = _build_floor_mesh(
            f"Floor_{pr.name}_{idx}",
            pts_m,
            z_top_m,
            thick_m,
            rooms_col,
            pr.is_slab,
            mat=floor_mat,
            pattern_rotation_deg=pr.pattern_rotation,
            pattern_scale=pr.pattern_scale,
        )
        holes_for_room = room_cutouts.get(pr.identifier, [])
        if floor_obj is not None:
            floor_obj["ESTISKETCH_ID"] = pr.identifier
            floor_holes = [h.points for h in holes_for_room if h.cuts_floor]
            cutout_count += _apply_slab_cutouts(
                floor_obj, floor_holes, z_top_m - thick_m, z_top_m, cx, cy, scene
            )
            room_count += 1

        if pr.height > 0.0:
            z_ceil_m = (lvl.elevation + pr.height) * INCH_TO_M
            ceil_thick_m = 0.5 * INCH_TO_M
            ceil_obj = _build_ceiling_mesh(
                f"Ceiling_{pr.name}_{idx}",
                pts_m,
                z_ceil_m,
                ceil_thick_m,
                ceilings_col,
                scene,
            )
            if ceil_obj is not None:
                ceil_obj["ESTISKETCH_ID"] = pr.identifier
                ceil_holes = [h.points for h in holes_for_room if h.cuts_ceiling]
                cutout_count += _apply_slab_cutouts(
                    ceil_obj, ceil_holes, z_ceil_m, z_ceil_m + ceil_thick_m, cx, cy, scene
                )
                ceiling_count += 1

    stair_count = 0
    railing_count = 0
    for ps in project.stairs:
        start_lvl = level_by_id.get(ps.start_level_id, level_by_id.get(ps.level_id, project.levels[0]))
        stairs_col = level_cols[start_lvl.id]["stairs"]
        stair_obj = _build_stair_object(ps, start_lvl, cx, cy, stairs_col, ops_stairs)
        if stair_obj is not None:
            stair_count += 1
        rail_paths = compute_stair_railing_paths_3d(ps, start_lvl.elevation)
        rail_obj = _build_stair_railing_mesh(
            f"Railing_{ps.identifier}", rail_paths, ps.rail_height, cx, cy, stairs_col
        )
        if rail_obj is not None:
            rail_obj["ESTISKETCH_ID"] = ps.identifier
            railing_count += 1

    ext_mat_by_level: Dict[str, object] = {}
    for pw in project.walls:
        if pw.exterior_wall and not pw.symbolic and pw.level_id not in ext_mat_by_level:
            lf, rf = _resolve_wall_side_finishes(pw)
            use_fin = rf if rf.lower() != "drywall" else lf
            if use_fin.lower() != "drywall":
                ext_mat_by_level[pw.level_id] = _get_or_create_wall_finish_material(
                    use_fin, None, surface_materials
                )

    roof_count = 0
    infill_count = 0
    for r_idx, prf in enumerate(project.roofs):
        solved = solve_roof_3d(prf, project)
        lvl = level_by_id.get(solved.level_id, project.levels[0])
        roofs_col = level_cols[lvl.id]["roofs"]
        roof_obj = _build_roof_mesh(f"Roof_{prf.roof_type}_{r_idx}", solved, cx, cy, roofs_col)
        if roof_obj is not None:
            roof_count += 1
        for i_idx, infill in enumerate(solved.gable_infills):
            infill_lvl = level_by_id.get(infill.level_id, lvl)
            walls_col = level_cols[infill_lvl.id]["walls"]
            infill_mat = ext_mat_by_level.get(infill_lvl.id)
            infill_obj = _build_gable_infill_mesh(
                f"GableInfill_{r_idx}_{i_idx}",
                infill,
                cx,
                cy,
                walls_col,
                scene,
                mat=infill_mat,
            )
            if infill_obj is not None:
                infill_count += 1

    cabinet_count = 0
    countertop_count = 0
    appliance_count = 0
    plumbing_count = 0
    furniture_count = 0
    for fx in project.fixtures:
        lvl = level_by_id.get(fx.level_id, project.levels[0])
        sym = fx.symbol_type
        if sym in _HB5_CABINET_SYMBOLS:
            cab_obj = _build_hb5_cabinet(
                fx,
                lvl,
                cx,
                cy,
                level_cols[lvl.id]["cabinets"],
                types_frameless,
                solver_frameless,
            )
            if cab_obj is not None:
                cabinet_count += 1
                _tag_corner_origin_fixture(cab_obj, fx)
        elif sym in _HB5_APPLIANCE_SYMBOLS:
            app_obj = _build_hb5_appliance(
                fx,
                lvl,
                cx,
                cy,
                level_cols[lvl.id]["cabinets"],
                types_appliances,
                appliance_geo,
            )
            if app_obj is not None:
                appliance_count += 1
                _tag_corner_origin_fixture(app_obj, fx)
        elif sym in _PLUMBING_MECHANICAL_SYMBOLS:
            pm_obj = _build_plumbing_mechanical_mesh(
                fx, lvl, cx, cy, level_cols[lvl.id]["plumbing"]
            )
            if pm_obj is not None:
                plumbing_count += 1
        else:
            furn_obj = _build_furniture_mesh(
                fx, lvl, cx, cy, level_cols[lvl.id]["furniture"]
            )
            if furn_obj is not None:
                furniture_count += 1

        if fx.has_countertop:
            ct_obj = _build_countertop_mesh(
                fx, lvl, cx, cy, level_cols[lvl.id]["cabinets"]
            )
            if ct_obj is not None:
                countertop_count += 1

    bpy.context.view_layer.update()

    custom_asset_count = 0
    live_sync = _load_live_sync_module() if sync_dir else None
    if live_sync is not None and custom_assets_json:
        custom_asset_count = live_sync.import_custom_assets(
            custom_assets_json, (cx, cy), root_col
        )
        bpy.context.view_layer.update()
    placeholder_count = _ensure_solid_fixtures(project.fixtures)

    if save_blend_path:
        bpy.ops.wm.save_as_mainfile(filepath=save_blend_path)
    if live_sync is not None:
        live_sync.tag_generated_objects((cx, cy))
        live_sync.install_save_handler(sync_dir)

    if not bpy.app.background:
        _schedule_viewport_frame()

    return {
        "levels": len(project.levels),
        "walls": wall_count,
        "doors": door_count,
        "windows": window_count,
        "rooms": room_count,
        "ceilings": ceiling_count,
        "roofs": roof_count,
        "gable_infills": infill_count,
        "stairs": stair_count,
        "railings": railing_count,
        "floor_cutouts": cutout_count,
        "cabinets": cabinet_count,
        "countertops": countertop_count,
        "appliances": appliance_count,
        "plumbing_mechanical": plumbing_count,
        "furniture": furniture_count,
        "baseboards": baseboard_count,
        "footers": footer_count,
        "skipped_openings": len(project.skipped_openings),
        "custom_assets": custom_asset_count,
        "placeholders": placeholder_count,
    }


def _parse_cli_args(argv: List[str]) -> Tuple[str, str, str, str]:
    """Parse ``-- <project.xml> [--save-blend P] [--sync-dir D] [--custom-assets J]``."""
    if "--" in argv:
        args = argv[argv.index("--") + 1:]
    else:
        args = []
    if not args:
        raise SystemExit(
            "Usage: blender --python estisketch_to_hb5.py -- <project.xml> "
            "[--save-blend <out.blend>] [--sync-dir <dir>] [--custom-assets <json>]"
        )

    def _opt(flag: str) -> str:
        if flag in args:
            i = args.index(flag)
            if i + 1 < len(args):
                return args[i + 1]
        return ""

    return args[0], _opt("--save-blend"), _opt("--sync-dir"), _opt("--custom-assets")


if __name__ == "__main__":
    xml_arg, blend_arg, sync_arg, assets_arg = _parse_cli_args(sys.argv)
    stats = build_in_blender(
        xml_arg,
        save_blend_path=blend_arg,
        sync_dir=sync_arg,
        custom_assets_json=assets_arg,
    )
    print(f"EstiSketch -> HB5 import complete: {stats}")
