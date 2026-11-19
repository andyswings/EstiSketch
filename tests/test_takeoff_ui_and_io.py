"""Phase 8 tests: Takeoff dialog, controller, and project_io XML persistence."""
import os
import sys

import gi
gi.require_version("Gtk", "4.0")
import pytest  # noqa: E402

sys.path.insert(0, os.path.dirname(__file__))
from test_open_project import _create_mock_canvas  # noqa: E402

from EstiSketch.Dialogs.takeoff_dialog import TakeoffController, create_takeoff_dialog  # noqa: E402
from EstiSketch.project_io import open_project, save_project  # noqa: E402

FIXTURE_XML = os.path.join(os.path.dirname(__file__), "fixtures", "simple_house.xml")


def _load_house():
    c = _create_mock_canvas()
    c.blueprints = []
    c.dimension_chains = []
    c.leader_callouts = []
    open_project(c, FIXTURE_XML)
    return c


def test_open_legacy_xml_initializes_empty_takeoff_state():
    c = _load_house()
    assert c.takeoff_state == {
        "assumptions": {},
        "overrides": {},
        "custom_items": [],
        "reference": None,
    }


def test_controller_override_stale_keep_and_reset():
    c = _load_house()
    ctrl = TakeoffController(c)
    assert len(ctrl.result.results) == 52
    assert ctrl.result.by_id("roofing_nails").computed == 5600

    # Set override
    ctrl.set_override("roofing_nails", 6000)
    lr = ctrl.result.by_id("roofing_nails")
    assert lr.final == 6000 and lr.override == 6000 and not lr.stale

    # Change assumption -> computed changes -> override becomes stale
    ctrl.set_assumption("nails_per_square", 380)
    lr = ctrl.result.by_id("roofing_nails")
    assert lr.computed == 5320 and lr.final == 6000 and lr.stale and lr.old_computed == 5600
    assert any(ch.name == "roofing_nails" and "stale" in ch.message for ch in ctrl.checks)

    # Keep override -> clears stale badge
    ctrl.keep_override("roofing_nails")
    lr = ctrl.result.by_id("roofing_nails")
    assert lr.final == 6000 and not lr.stale

    # Clear override -> reverts to computed
    ctrl.clear_override("roofing_nails")
    lr = ctrl.result.by_id("roofing_nails")
    assert lr.final == 5320 and lr.override is None


def test_controller_custom_items_and_reference():
    c = _load_house()
    ctrl = TakeoffController(c)

    cid = ctrl.add_custom_item("Hurricane ties", "Roof Framing", 42, "ea")
    assert ctrl.result.by_id(cid).final == 42
    assert ctrl.result.by_id(cid).item.description == "Hurricane ties"

    ref = ctrl.save_reference("checked_house")
    assert ref.values[cid] == 42
    assert ctrl.get_reference().name == "checked_house"

    ctrl.remove_custom_item(cid)
    with pytest.raises(KeyError):
        ctrl.result.by_id(cid)


def test_project_io_roundtrips_takeoff_state(tmp_path):
    c = _load_house()
    ctrl = TakeoffController(c)
    ctrl.set_assumption("nails_per_square", 380)
    ctrl.set_override("framing_nails", 1500)
    ctrl.add_custom_item("Extra lumber", "Framing", 4, "ea")
    ctrl.save_reference("my_ref")

    out_path = tmp_path / "saved_with_takeoff.xml"
    save_project(c, 1280, 800, str(out_path))

    c2 = _create_mock_canvas()
    c2.blueprints = []
    c2.dimension_chains = []
    c2.leader_callouts = []
    open_project(c2, str(out_path))

    assert c2.takeoff_state["assumptions"]["nails_per_square"] == 380.0
    assert c2.takeoff_state["overrides"]["framing_nails"]["value"] == 1500.0
    assert len(c2.takeoff_state["custom_items"]) == 1
    assert c2.takeoff_state["reference"]["name"] == "my_ref"

    ctrl2 = TakeoffController(c2)
    assert ctrl2.result.by_id("roofing_nails").computed == 5320
    assert ctrl2.result.by_id("framing_nails").final == 1500
    assert ctrl2.result.by_id("custom_1").final == 4


def test_create_takeoff_dialog_builds_without_error():
    c = _load_house()
    win = create_takeoff_dialog(None, c)
    try:
        assert win._controller.result.by_id("rebar_20").computed == 68
        assert win._controller.result.by_id("shingles").computed == 14
    finally:
        win.destroy()


def test_ceiling_type_flat_vs_vaulted_and_global_default():
    from types import SimpleNamespace

    c = _load_house()
    ctrl = TakeoffController(c)
    assert ctrl.get_ceiling_type() == "vaulted"
    vaulted_drywall = ctrl.result.by_id("drywall_sqft").computed

    ctrl.set_ceiling_type("flat")
    assert ctrl.get_ceiling_type() == "flat"
    flat_drywall = ctrl.result.by_id("drywall_sqft").computed
    assert flat_drywall < vaulted_drywall
    # Flat ceiling excludes gable triangles and roof pitch slope factor
    assert c.takeoff_state["assumptions"]["ceiling_vaulted"] == 0.0
    assert c.takeoff_state["assumptions"]["include_gable_walls_in_interior"] == 0.0

    # Global config default applies when project hasn't overridden ceiling_vaulted
    c2 = _load_house()
    c2.config = SimpleNamespace(TAKEOFF_CEILING_TYPE="flat")
    ctrl2 = TakeoffController(c2)
    assert ctrl2.get_ceiling_type() == "flat"
    assert ctrl2.result.by_id("drywall_sqft").computed == flat_drywall

