import ctypes

import pytest

from txtest.services.credentials import WinRMCredentials, WindowsCredentialPrompt, detect_current_operator


class _FakeFunction:
    def __init__(self, impl):
        self.impl = impl
        self.argtypes = None
        self.restype = None

    def __call__(self, *args):
        return self.impl(*args)


class _FakeCredUi:
    def __init__(self) -> None:
        self.freed_pointer = None
        self.CredUIPromptForWindowsCredentialsW = _FakeFunction(self._prompt)
        self.CredUnPackAuthenticationBufferW = _FakeFunction(self._unpack)
        self.CredFree = _FakeFunction(self._free)

    def _prompt(self, *_args):
        out_auth_buffer = ctypes.cast(_args[5], ctypes.POINTER(ctypes.c_void_p))
        out_auth_buffer.contents.value = 1234
        out_auth_buffer_size = ctypes.cast(_args[6], ctypes.POINTER(ctypes.c_ulong))
        out_auth_buffer_size.contents.value = 64
        return 0

    def _unpack(self, *_args):
        username = _args[3]
        domain = _args[5]
        password = _args[7]
        username.value = "operator1"
        domain.value = "DOMAIN"
        password.value = "secret"
        return True

    def _free(self, pointer):
        self.freed_pointer = pointer


def test_windows_credential_prompt_frees_native_buffer_with_pointer_value(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_credui = _FakeCredUi()
    monkeypatch.setattr("txtest.services.credentials.sys.platform", "win32")
    monkeypatch.setattr("txtest.services.credentials.ctypes.WinDLL", lambda *_args, **_kwargs: fake_credui)

    credentials = WindowsCredentialPrompt().prompt("target", "message")

    assert credentials == WinRMCredentials(username="DOMAIN\\operator1", password="secret")
    assert fake_credui.freed_pointer == 1234


def test_detect_current_operator_prefers_dns_domain(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("USERNAME", "krystian.hettman")
    monkeypatch.setenv("USERDNSDOMAIN", "stako.local")
    monkeypatch.setenv("USERDOMAIN", "STAKO")

    assert detect_current_operator() == "stako.local\\krystian.hettman"


def test_detect_current_operator_falls_back_to_userdomain(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("USERNAME", "krystian.hettman")
    monkeypatch.delenv("USERDNSDOMAIN", raising=False)
    monkeypatch.setenv("USERDOMAIN", "STAKO")

    assert detect_current_operator() == "STAKO\\krystian.hettman"
