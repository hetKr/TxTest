from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import pytest

from txtest.models.core import TransportResult
from txtest.services.audit import AuditService
from txtest.services.config_loader import ConfigLoader
from txtest.services.orchestrator import Orchestrator
from txtest.services.reporting import ReportService
from txtest.services.state_store import QueueStateStore
from txtest.services.winrm import MockTransport, WinRMClient


ROOT = Path(__file__).resolve().parents[1]


def _build_transport_payload(test_name: str, hostname: str) -> str:
    payload = {
        "test_name": test_name,
        "status": "PASS",
        "message": f"{test_name} completed",
        "value": test_name,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "duration_ms": 25,
        "error_code": None,
        "severity": "INFO",
        "details": {"source": "pytest"},
        "host_info": {"hostname": hostname, "ip": "127.0.0.1"},
        "script_version": "1.0.0",
        "attempt_no": 1,
        "artifacts": [],
    }
    return json.dumps(payload)


def build_test_orchestrator(repo_root: Path, state_dir: Path) -> Orchestrator:
    loader = ConfigLoader()
    stations = loader.load_stations(repo_root / "configs" / "stations.yaml")
    packages = loader.load_packages(repo_root / "configs" / "packages.yaml")
    station = stations.stations[0]
    responses = {
        f"{station.host}:{script_path.name}": TransportResult(
            stdout=_build_transport_payload(script_path.stem, station.host),
            stderr="",
            exit_code=0,
        )
        for script_path in (repo_root / "scripts").glob("*.ps1")
    }
    transport = MockTransport(responses)
    return Orchestrator(
        QueueStateStore(state_dir),
        stations_config=stations,
        packages_config=packages,
        report_service=ReportService(repo_root / "reports"),
        audit_service=AuditService(repo_root / "audit"),
        winrm_client=WinRMClient(transport=transport),
        config_loader=loader,
        scripts_dir=repo_root / "scripts",
    )


@pytest.fixture
def test_repo_root() -> Path:
    return ROOT


@pytest.fixture
def workspace_temp_dir(test_repo_root: Path):
    path = Path.home() / "AppData" / "Local" / "Temp" / f"txtest-pytest-{uuid4()}"
    path.mkdir(parents=True, exist_ok=True)
    yield path


@pytest.fixture
def mock_orchestrator(workspace_temp_dir: Path, test_repo_root: Path) -> Orchestrator:
    return build_test_orchestrator(test_repo_root, workspace_temp_dir)
