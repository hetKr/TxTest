from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator, model_validator


SCHEMA_VERSION = "1.0.0"
SUPPORTED_SCHEMA_VERSIONS = {"1.0.0"}


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


class TestState(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    RETRY_SCHEDULED = "RETRY_SCHEDULED"
    FINISHED = "FINISHED"
    CANCELLED_TECHNICAL = "CANCELLED_TECHNICAL"
    FAILED_TO_START = "FAILED_TO_START"


class Severity(str, Enum):
    CRITICAL = "CRITICAL"
    WARNING = "WARNING"
    INFO = "INFO"


class HostInfo(BaseModel):
    hostname: str
    ip: str | None = None


class Artifact(BaseModel):
    name: str
    path: str
    content_type: str | None = None


class ScriptResult(BaseModel):
    test_name: str
    status: DomainStatus
    message: str
    value: str | None = None
    timestamp_utc: datetime
    duration_ms: int = Field(ge=0)
    error_code: str | None = None
    severity: Severity
    details: dict[str, Any] = Field(default_factory=dict)
    host_info: HostInfo
    script_version: str
    attempt_no: int = Field(ge=1)
    artifacts: list[Artifact] = Field(default_factory=list)

    @field_validator("timestamp_utc")
    @classmethod
    def ensure_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("timestamp_utc must be timezone aware")
        return value.astimezone(timezone.utc)


class StationDefinition(BaseModel):
    station_id: str
    station_name: str
    host: str
    ip: str
    auth: Literal["kerberos", "ntlm", "credssp"]
    tags: list[str] = Field(default_factory=list)


class StationsConfig(BaseModel):
    schema_version: str
    stations: list[StationDefinition]

    @model_validator(mode="after")
    def validate_schema_and_uniqueness(self) -> "StationsConfig":
        if self.schema_version not in SUPPORTED_SCHEMA_VERSIONS:
            raise ValueError(f"Unsupported stations schema_version: {self.schema_version}")
        station_ids = [station.station_id for station in self.stations]
        if len(station_ids) != len(set(station_ids)):
            raise ValueError("station_id values must be unique")
        return self


class PackageTestDefinition(BaseModel):
    name: str
    manifest: str
    timeout_seconds: int = Field(gt=0)
    retry_count: int = Field(ge=0)
    retry_backoff_seconds: int = Field(ge=0)
    continue_on_fail: bool
    severity: Severity
    tags: list[str] = Field(default_factory=list)
    resource_locks: list[str] = Field(default_factory=list)
    parallel_group: str | None = None
    parameters: dict[str, Any] = Field(default_factory=dict)


class PackageDefinition(BaseModel):
    package_name: str
    description: str
    max_parallel_stations: int = Field(default=3, ge=1)
    tests: list[PackageTestDefinition]


class PackagesConfig(BaseModel):
    schema_version: str
    packages: list[PackageDefinition]

    @model_validator(mode="after")
    def validate_schema(self) -> "PackagesConfig":
        if self.schema_version not in SUPPORTED_SCHEMA_VERSIONS:
            raise ValueError(f"Unsupported packages schema_version: {self.schema_version}")
        return self


class ScriptParameter(BaseModel):
    name: str
    type: str
    required: bool
    default: Any | None = None
    description: str = ""


class ScriptManifest(BaseModel):
    name: str
    version: str
    schema_version: str
    min_app_version: str
    description: str
    script_file: str
    tags: list[str] = Field(default_factory=list)
    severity: Severity
    supports_parallel: bool = False
    parameters: list[ScriptParameter] = Field(default_factory=list)
    conditions: list[dict[str, Any]] = Field(default_factory=list)


class AuditEntry(BaseModel):
    audit_id: str = Field(default_factory=lambda: str(uuid4()))
    timestamp_utc: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    operator: str
    action: str
    target_type: str
    target_id: str
    run_id: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)


class RunSummary(BaseModel):
    passed: int = 0
    failed: int = 0
    skipped: int = 0
    errors: int = 0
    timeouts: int = 0


class AttemptSummary(BaseModel):
    total_attempts: int = 0
    retried_tests: int = 0


class PackageRunReport(BaseModel):
    run_id: str
    correlation_id: str
    station_id: str
    station_name: str
    package_name: str
    operator: str
    config_version: str
    started_at_utc: datetime
    finished_at_utc: datetime | None = None
    duration_ms: int = 0
    final_status: DomainStatus | None = None
    termination_reason: TerminationReason | None = None
    forced_after_preflight_warning: bool = False
    environment_snapshot: dict[str, Any] = Field(default_factory=dict)
    results: list[ScriptResult] = Field(default_factory=list)
    summary: RunSummary = Field(default_factory=RunSummary)
    event_log: list[dict[str, Any]] = Field(default_factory=list)
    attempt_summary: AttemptSummary = Field(default_factory=AttemptSummary)


class QueueRun(BaseModel):
    run_id: str
    correlation_id: str
    station_id: str
    package_name: str
    operator: str
    forced_after_preflight_warning: bool = False
    cancellation_requested: bool = False
    state: RunState = RunState.QUEUED
    final_status: DomainStatus | None = None
    termination_reason: TerminationReason | None = None
