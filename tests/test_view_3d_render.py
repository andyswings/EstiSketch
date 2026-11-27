"""Headless EGL/Mesa offscreen visual regression tests for the native 3D renderer."""

from __future__ import annotations

from pathlib import Path
import struct

import pytest

from EstiSketch import native_3d
from EstiSketch.scene_ir import SceneIR, build_scene_ir_from_xml

REPO_ROOT = Path(__file__).resolve().parent.parent
DEMO_DIR = REPO_ROOT / "examples" / "demo_houses"
DEMO_HOUSES = (
    DEMO_DIR / "house1_gable_2bed_1_5bath_1200sqft.xml",
    DEMO_DIR / "house2_two_story_3bed_2bath_garage_1800sqft.xml",
    DEMO_DIR / "house3_l_shape_2bed_2bath_office_1500sqft.xml",
)


def _load_session(xml_path: Path) -> tuple[native_3d.NativeSceneSessionProtocol, SceneIR]:
    scene = build_scene_ir_from_xml(str(xml_path))
    session = native_3d.create_native_session()
    session.load_scene(scene.to_json())
    session.set_camera_preset("iso")
    return session, scene


def _render_or_skip(
    session: native_3d.NativeSceneSessionProtocol,
    width: int = 320,
    height: int = 240,
) -> bytes:
    try:
        return session.render_offscreen_rgba(width, height)
    except RuntimeError as exc:
        msg = str(exc)
        if any(tok in msg for tok in ("EGL", "libEGL", "surfaceless", "config", "context")):
            pytest.skip(f"Headless EGL driver unavailable in environment: {msg}")
        raise


def _mean_luma(rgba: bytes) -> float:
    total = 0.0
    pixels = len(rgba) // 4
    for idx in range(0, len(rgba), 4):
        total += 0.2126 * rgba[idx] + 0.7152 * rgba[idx + 1] + 0.0722 * rgba[idx + 2]
    return total / max(1, pixels)


def _pixel_diff_count(buf_a: bytes, buf_b: bytes, threshold: int = 8) -> int:
    diffs = 0
    for idx in range(0, len(buf_a), 4):
        dr = abs(buf_a[idx] - buf_b[idx])
        dg = abs(buf_a[idx + 1] - buf_b[idx + 1])
        db = abs(buf_a[idx + 2] - buf_b[idx + 2])
        if dr + dg + db > threshold:
            diffs += 1
    return diffs


@pytest.mark.skipif(
    not native_3d.is_native_3d_available(), reason="compiled _native_3d extension unavailable"
)
def test_offscreen_render_all_three_demo_houses(tmp_path: Path) -> None:
    """Every bundled demo house renders cleanly to valid RGBA & PNG images offscreen."""
    width, height = 320, 240
    for xml_path in DEMO_HOUSES:
        session, _scene = _load_session(xml_path)
        rgba = _render_or_skip(session, width, height)
        assert len(rgba) == width * height * 4

        # Ensure rich non-uniform shaded output (sky + horizon + illuminated building)
        sample_colors = {
            rgba[idx:idx + 3]  # noqa: E203
            for idx in range(0, len(rgba), 64 * 4)
        }
        assert len(sample_colors) > 25

        out_png = tmp_path / f"{xml_path.stem}.png"
        nbytes = native_3d.write_rgba_png(out_png, width, height, rgba)
        assert nbytes > 200
        png_bytes = out_png.read_bytes()
        assert png_bytes[:8] == b"\x89PNG\r\n\x1a\n"
        ihdr_w, ihdr_h = struct.unpack("!II", png_bytes[16:24])
        assert (ihdr_w, ihdr_h) == (width, height)


@pytest.mark.skipif(
    not native_3d.is_native_3d_available(), reason="compiled _native_3d extension unavailable"
)
def test_offscreen_styles_ssao_roof_hide_and_selection_highlight() -> None:
    """Verify SSAO darkening, all 4 render styles, auto-hide roofs, and selection highlight."""
    width, height = 240, 180
    session, scene = _load_session(DEMO_HOUSES[0])

    # 1. All 4 visual styles produce visibly distinct renders
    renders: dict[str, bytes] = {}
    for style in ("textured", "clay", "sketch", "xray"):
        session.set_render_style(style)
        renders[style] = _render_or_skip(session, width, height)
    for idx, s1 in enumerate(("textured", "clay", "sketch", "xray")):
        for s2 in ("textured", "clay", "sketch", "xray")[idx + 1:]:  # noqa: E203
            assert _pixel_diff_count(renders[s1], renders[s2]) > 500

    # 2. SSAO adds genuine crevice ambient occlusion in Clay mode (strictly lower mean luma)
    session.set_render_style("clay")
    session.set_ssao_enabled(True)
    assert session.ssao_enabled() is True
    with_ssao = _render_or_skip(session, width, height)

    session.set_ssao_enabled(False)
    assert session.ssao_enabled() is False
    without_ssao = _render_or_skip(session, width, height)
    assert _pixel_diff_count(with_ssao, without_ssao, threshold=4) > 200
    assert _mean_luma(with_ssao) < _mean_luma(without_ssao)

    # 3. Auto-hide roofs in Top view reveals interior floorplan
    session.set_ssao_enabled(True)
    session.set_render_style("textured")
    session.set_camera_preset("top")
    session.set_auto_hide_roofs(False)
    roof_shown = _render_or_skip(session, width, height)
    session.set_auto_hide_roofs(True)
    roof_hidden = _render_or_skip(session, width, height)
    assert _pixel_diff_count(roof_shown, roof_hidden) > 1000

    # 4. Selection highlight visibly changes pixels in 3D view
    session.set_camera_preset("iso")
    session.set_selected_entities([])
    unselected = _render_or_skip(session, width, height)
    first_wall_id = scene.walls[0].id
    session.set_selected_entities([first_wall_id])
    selected = _render_or_skip(session, width, height)
    assert _pixel_diff_count(unselected, selected) > 150
