import pytest
import importlib


def test_version_import():
    # Ensure the version module can be imported and has the expected attribute
    try:
        version = importlib.import_module("EstiSketch.version")
    except ImportError:
        pytest.fail("version module not found")
    assert hasattr(version, "__version__"), "__version__ attribute missing"
    assert version.__version__ == "0.2.0-alpha", "Version string mismatch"


def test_main_import():
    # Import the main module to ensure it loads without syntax errors
    try:
        main = importlib.import_module("EstiSketch.main")
    except Exception as e:
        pytest.fail(f"Failed to import main: {e}")
