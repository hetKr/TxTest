import json

import pytest

from txtest.services.result_parser import InvalidJsonResultError, ResultParser


VALID = json.dumps(
    {
        "test_name": "disk_free_space",
        "status": "PASS",
        "message": "ok",
        "value": "10 GB",
        "timestamp_utc": "2026-03-23T10:15:30Z",
        "duration_ms": 10,
        "error_code": None,
        "severity": "INFO",
        "details": {},
        "host_info": {"hostname": "ST01", "ip": "192.168.1.15"},
        "script_version": "1.0.0",
        "attempt_no": 1,
        "artifacts": [],
    }
)


def test_parse_valid_result() -> None:
    result = ResultParser().parse_stdout(VALID)
    assert result.status.value == "PASS"


def test_parse_invalid_result() -> None:
    with pytest.raises(InvalidJsonResultError):
        ResultParser().parse_stdout("not-json")
