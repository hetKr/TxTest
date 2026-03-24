from pathlib import Path

from txtest.services.config_loader import ConfigLoader


ROOT = Path(__file__).resolve().parents[1]


def test_load_stations_config() -> None:
    loader = ConfigLoader()
    stations = loader.load_stations(ROOT / "configs" / "stations.yaml")
    assert stations.schema_version == "1.0.0"
    assert stations.stations[0].host == "PLSLU-BP8D1G3.stako.local"


def test_load_packages_config() -> None:
    loader = ConfigLoader()
    packages = loader.load_packages(ROOT / "configs" / "packages.yaml")
    assert packages.packages[0].package_name == "basic_healthcheck"
