from __future__ import annotations

from pathlib import Path

from txtest.constants import CONFIGS_DIR
from txtest.services.audit import AuditService
from txtest.services.config_loader import ConfigLoader
from txtest.services.orchestrator import Orchestrator
from txtest.services.reporting import ReportService
from txtest.services.state_store import QueueStateStore
from txtest.services.winrm import WinRMClient


def build_orchestrator(repo_root: Path) -> Orchestrator:
    loader = ConfigLoader()
    stations = loader.load_stations(repo_root / CONFIGS_DIR / "stations.yaml")
    packages = loader.load_packages(repo_root / CONFIGS_DIR / "packages.yaml")

    if not stations.stations:
        raise ValueError("No stations defined in configs/stations.yaml")
    if not packages.packages:
        raise ValueError("No packages defined in configs/packages.yaml")

    return Orchestrator(
        QueueStateStore(repo_root / ".runtime"),
        stations_config=stations,
        packages_config=packages,
        report_service=ReportService(repo_root / "reports"),
        audit_service=AuditService(repo_root / "audit"),
        winrm_client=WinRMClient(),
        config_loader=loader,
        scripts_dir=repo_root / "scripts",
    )
