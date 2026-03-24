from pathlib import Path

APP_NAME = "TxTest"
APP_VERSION = "1.0.0"
SUPPORTED_SCHEMA_VERSION = "1.0.0"
SUPPORTED_SCHEMA_MAJOR = 1
DEFAULT_MAX_PARALLEL_STATIONS = 3
RUNTIME_STATE_FILE = Path("reports/runtime_state.json")
AUDIT_LOG_FILE = Path("audit/audit_log.jsonl")
REPORTS_DIR = Path("reports")
SCRIPTS_DIR = Path("scripts")
CONFIGS_DIR = Path("configs")
