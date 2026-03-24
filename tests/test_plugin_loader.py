from pathlib import Path

from txtest.services.plugin_loader import PluginLoader


ROOT = Path(__file__).resolve().parents[1]


def test_discover_manifests() -> None:
    loader = PluginLoader()
    manifests = loader.discover(ROOT / "scripts")
    assert "preflight_check" in manifests
    assert manifests["disk_free_space"].script_file == "disk_free_space.ps1"
