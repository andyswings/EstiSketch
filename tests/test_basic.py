import importlib
import json
import os
from types import SimpleNamespace

import pytest


def test_version_import():
    # Ensure the version module can be imported and has the expected attribute
    try:
        version = importlib.import_module("EstiSketch.version")
    except ImportError:
        pytest.fail("version module not found")
    assert hasattr(version, "__version__"), "__version__ attribute missing"
    assert version.__version__ == "0.4.0-beta", "Version string mismatch"


def test_main_import():
    # Import the main module to ensure it loads without syntax errors
    try:
        importlib.import_module("EstiSketch.main")
    except Exception as e:
        pytest.fail(f"Failed to import main: {e}")


def test_config_load_merges_defaults(tmp_path, monkeypatch):
    from EstiSketch import config

    cfg_file = tmp_path / "nested" / "settings.json"
    cfg_file.parent.mkdir(parents=True)
    cfg_file.write_text(json.dumps({"UNITS": "metric", "WINDOW_WIDTH": 1280}), encoding="utf-8")

    monkeypatch.setattr(config, "CONFIG_FILE", str(cfg_file))
    loaded = config.load_config()

    assert loaded["UNITS"] == "metric"
    assert loaded["WINDOW_WIDTH"] == 1280
    assert loaded["FLOORING_WASTE_PCT"] == config.DEFAULT_SETTINGS["FLOORING_WASTE_PCT"]


def test_config_save_creates_parent_dirs(tmp_path, monkeypatch):
    from EstiSketch import config

    cfg_file = tmp_path / "user_cfg" / "estisketch" / "settings.json"
    monkeypatch.setattr(config, "CONFIG_FILE", str(cfg_file))

    config.save_config({"UNITS": "metric", "DEBUG": True})

    assert cfg_file.exists()
    written = json.loads(cfg_file.read_text(encoding="utf-8"))
    assert written == {"UNITS": "metric", "DEBUG": True}


def test_app_save_settings_uses_user_config_not_package_dir(tmp_path, monkeypatch):
    from EstiSketch import config, main

    cfg_file = tmp_path / "estisketch" / "settings.json"
    monkeypatch.setattr(config, "CONFIG_FILE", str(cfg_file))

    pkg_settings = os.path.join(os.path.dirname(main.__file__), "settings.json")
    pkg_before = os.path.getmtime(pkg_settings) if os.path.exists(pkg_settings) else None

    fake_app = SimpleNamespace(
        config=SimpleNamespace(
            WINDOW_WIDTH=1440,
            WINDOW_HEIGHT=900,
            WINDOW_MAXIMIZED=True,
            SIDEBAR_WIDTH=340,
            LAYERS_PROPERTIES_SPLIT=250,
            SHOW_PROPERTIES_PANEL=False,
        )
    )

    main.EstimatorApp._save_settings(fake_app)

    assert cfg_file.exists()
    saved = json.loads(cfg_file.read_text(encoding="utf-8"))
    assert saved["WINDOW_WIDTH"] == 1440
    assert saved["WINDOW_MAXIMIZED"] is True
    assert saved["SIDEBAR_WIDTH"] == 340
    assert saved["SHOW_PROPERTIES_PANEL"] is False
    if pkg_before is not None:
        assert os.path.getmtime(pkg_settings) == pkg_before


def test_main_version_flag(capsys):
    from EstiSketch import main

    main.main(["--version"])
    captured = capsys.readouterr()
    assert "EstiSketch 0.4.0-beta" in captured.out
