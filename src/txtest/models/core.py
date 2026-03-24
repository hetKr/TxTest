from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator, model_validator

from txtest.constants import APP_VERSION, DEFAULT_MAX_PARALLEL_STATIONS, SUPPORTED_SCHEMA_MAJOR


class DomainStatus(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    SKIPPED = "SKIPPED"
    ERROR = "ERROR"
    TIMEOUT = "TIMEOUT"
    ABORTED = "ABORTED"
    AUTH_FAILED = "AUTH_FAILED"
    UNREACHABLE = "UNREACHABLE"
    INVALID_OUTPUT = "INVALID_OUTPUT"


class TerminationReason(str, Enum):
    COMPLETED = "COMPLETED"
    FAIL_FAST = "FAIL_FAST"
    OPERATOR_CANCEL = "OPERATOR_CANCEL"
    PRECHECK_REJECTED = "PRECHECK_REJECTED"
    STARTUP_ERROR = "STARTUP_ERROR"
    INFRASTRUCTURE_ERROR = "INFRASTRUCTURE_ERROR"
    RECOVERY_AFTER_RESTART = "RECOVERY_AFTER_RESTART"


class RunState(str, Enum):
    QUEUED = "QUEUED"
    PRECHECK_RUNNING = "PRECHECK_RUNNING"
    WAITING_FOR_OPERATOR_CONFIRMATION = "WAITING_FOR_OPERATOR_CONFIRMATION"
    READY = "READY"
    RUNNING = "RUNNING"
    CANCELLATION_REQUESTED = "CANCELLATION_REQUESTED"
    CANCELLING = "CANCELLING"
    FINISHED = "FINISHED"
    FAILED_TO_START = "FAILED_TO_START"


class TestTechState(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    RETRY_SCHEDULED = "RETRY_SCHEDULED"
    FINISHED = "FINISHED"
    CANCELLED_TECHNICAL = "CANCELLED_TECHNICAL"
    FAILED_TO_START = "FAILED_TO_START"


class TestSeverity(str, Enum):
    CRITICAL = "CRITICAL"
    WARNING = "WARNING"
    INFO = "INFO"


class BackoffMode(str, Enum):
    FIXED = "fixed"
    EXPONENTIAL = "exponential"


class TargetType(str, Enum):
    RUN = "RUN"
    CONFIG = "CONFIG"
    PACKAGE = "PACKAGE"


class StationDefinition(BaseModel):
    station_id: str
    station_name: str
    hostname: str
    ip: str
    auth: Literal["kerberos", "ntlm", "credssp"] = "kerberos"
    tags: list[str] = Field(default_factory=list)


class ParameterDefinition(BaseModel):
    name: str
    type: Literal["string", "int", "float", "bool"]
    required: bool = True
    default: Any | None = None
    description: str = ""


class ConditionDefinition(BaseModel):
    type: str
    parameter: str | None = None


class ManifestDefinition(BaseModel):
    name: str
    version: str
    schema_version: str
    min_app_version: str
    description: str
    script_file: str
    tags: list[str] = Field(default_factory=list)
    severity: TestSeverity
    supports_parallel: bool = False
    parameters: list[ParameterDefinition] = Field(default_factory=list)
    conditions: list[ConditionDefinition] = Field(default_factory=list)

    @field_validator("schema_version")
    @classmethod
    def validate_manifest_version(cls, value: str) -> str:
        if int(value.split(".")[0]) > SUPPORTED_SCHEMA_MAJOR:
            raise ValueError(f"Unsupported manifest schema_version '{value}'")
        return value

    @field_validator("min_app_version")
    @classmethod
    def validate_min_app_version(cls, value: str) -> str:
        if tuple(map(int, value.split("."))) > tuple(map(int, APP_VERSION.split("."))):
            raise ValueError(f"Manifest requires app version {value} but app is {APP_VERSION}")
        return value


class TestDefinition(BaseModel):
    test_id: str
    manifest: str
    timeout_seconds: int = Field(gt=0)
    retry_count: int = Field(ge=0)
    retry_backoff_seconds: int = Field(ge=0)
    continue_on_fail: bool
    severity: TestSeverity
    tags: list[str] = Field(default_factory=list)
    resource_locks: list[str] = Field(default_factory=list)
    parameters: dict[str, Any] = Field(default_factory=dict)
    parallel_group: str | None = None
    run_conditions: list[ConditionDefinition] = Field(default_factory=list)


class PackageDefinition(BaseModel):
    package_name: str
    description: str
    tags: list[str] = Field(default_factory=list)
    tests: list[TestDefinition]


class AppConfig(BaseModel):
    schema_version: str
    stations: list[StationDefinition]
    packages: list[PackageDefinition]
    max_parallel_stations: int = DEFAULT_MAX_PARALLEL_STATIONS

    @field_validator("schema_version")
    @classmethod
    def validate_schema_version(cls, value: str) -> str:
        if int(value.split(".")[0]) > SUPPORTED_SCHEMA_MAJOR:
            raise ValueError(f"Unsupported config schema_version '{value}'")
        return value

    @model_validator(mode="after")
    def ensure_unique_station_ids(self) -> "AppConfig":
        ids = [station.station_id for station in self.stations]
        if len(ids) != len(set(ids)):
            raise ValueError("station_id values must be unique")
        return self


class HostInfo(BaseModel):
    hostname: str
    ip: str


class ArtifactMeta(BaseModel):
    name: str
    path: str
    content_type: str = "text/plain"


class ScriptExecutionResult(BaseModel):
    test_name: str
    status: DomainStatus
    message: str
    value: str | int | float | bool | None = None
    timestamp_utc: datetime
    duration_ms: int = Field(ge=0)
    error_code: str | None = None
    severity: TestSeverity
    details: dict[str, Any] = Field(default_factory=dict)
    host_info: HostInfo
    script_version: str
    attempt_no: int = Field(ge=1)
    artifacts: list[ArtifactMeta] = Field(default_factory=list)

    @field_validator("timestamp_utc", mode="before")
    @classmethod
    def parse_utc_datetime(cls, value: Any) -> datetime:
        if isinstance(value, datetime):
            return value.astimezone(UTC)
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(UTC)


class PackageResult(BaseModel):
    run_id: str
    correlation_id: str
    station_id: str
    station_name: str
    package_name: str
    operator: str
    config_version: str
    started_at_utc: datetime
    finished_at_utc: datetime
    duration_ms: int = Field(ge=0)
    final_status: DomainStatus
    termination_reason: TerminationReason
    forced_after_preflight_warning: bool = False
    environment_snapshot: dict[str, Any] = Field(default_factory=dict)
    results: list[ScriptExecutionResult] = Field(default_factory=list)
    summary: dict[str, int] = Field(default_factory=dict)
    event_log: list[dict[str, Any]] = Field(default_factory=list)
    attempt_summary: dict[str, int] = Field(default_factory=dict)


class SummaryCounters(BaseModel):
    passed: int = 0
    failed: int = 0
    skipped: int = 0
    errors: int = 0
    timeouts: int = 0


class PreflightSnapshot(BaseModel):
    cpu_percent: int = Field(ge=0, le=100)
    ram_percent: int = Field(ge=0, le=100)
    winrm_ok: bool
    host_responsive: bool
    warning: bool
    details: dict[str, Any] = Field(default_factory=dict)


class PreflightDecision(BaseModel):
    approved: bool
    forced_after_warning: bool = False
    snapshot: PreflightSnapshot


class TransportResult(BaseModel):
    exit_code: int
    stdout: str
    stderr: str = ""


class TestRunRecord(BaseModel):
    test_id: str
    state: TestTechState = TestTechState.PENDING
    attempts: int = 0
    domain_status: DomainStatus | None = None
    last_message: str = ""


class RunRecord(BaseModel):
    run_id: str
    correlation_id: str = Field(default_factory=lambda: str(uuid4()))
    station_id: str
    package_name: str
    operator: str
    state: RunState = RunState.QUEUED
    cancellation_requested: bool = False
    requires_reconciliation: bool = False
    forced_after_preflight_warning: bool = False
    created_at_utc: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at_utc: datetime = Field(default_factory=lambda: datetime.now(UTC))
    tests: list[TestRunRecord] = Field(default_factory=list)


class AuditEntry(BaseModel):
    audit_id: str = Field(default_factory=lambda: str(uuid4()))
    timestamp_utc: datetime = Field(default_factory=lambda: datetime.now(UTC))
    operator: str
    action: str
    target_type: TargetType
    target_id: str
    run_id: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)


class HtmlExportResult(BaseModel):
    path: str
    generated_at_utc: datetime = Field(default_factory=lambda: datetime.now(UTC))
