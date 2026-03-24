from pathlib import Path

from txtest.ui.app import TxTestApp


ROOT = Path(__file__).resolve().parents[1]


def test_ui_uses_config_driven_defaults() -> None:
    app = TxTestApp(ROOT)
    assert app.default_station_id == "ST01"
    assert app.default_package_name == "basic_healthcheck"
