from __future__ import annotations

import json

from pydantic import ValidationError

from txtest.models.domain import DomainStatus, ScriptResult


class InvalidJsonResultError(ValueError):
    def __init__(
        self,
        message: str,
        *,
        stdout: str | None = None,
        stderr: str | None = None,
        exit_code: int | None = None,
    ) -> None:
        super().__init__(message)
        self.stdout = stdout
        self.stderr = stderr
        self.exit_code = exit_code


class ResultParser:
    def parse_stdout(self, stdout: str) -> ScriptResult:
        try:
            payload = json.loads(stdout)
        except json.JSONDecodeError as exc:
            raise InvalidJsonResultError("Script did not return valid JSON") from exc
        try:
            return ScriptResult.model_validate(payload)
        except ValidationError as exc:
            raise InvalidJsonResultError("Script JSON does not match required schema") from exc

    @staticmethod
    def invalid_output_result(test_name: str, message: str) -> dict:
        return {"test_name": test_name, "status": DomainStatus.INVALID_OUTPUT.value, "message": message}
