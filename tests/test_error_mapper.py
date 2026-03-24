from txtest.models.domain import DomainStatus
from txtest.services.error_mapper import ErrorMapper, WinRMAuthError, WinRMUnreachableError


mapper = ErrorMapper()


def test_auth_error_mapping() -> None:
    assert mapper.map_exception(WinRMAuthError()) is DomainStatus.AUTH_FAILED


def test_unreachable_mapping() -> None:
    assert mapper.map_exception(WinRMUnreachableError()) is DomainStatus.UNREACHABLE


def test_timeout_is_transient() -> None:
    assert mapper.is_transient(TimeoutError()) is True
