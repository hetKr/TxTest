from __future__ import annotations

import ctypes
import getpass
import os
import sys
from ctypes import wintypes
from dataclasses import dataclass


@dataclass(slots=True)
class WinRMCredentials:
    username: str
    password: str


class CredentialPromptCancelledError(RuntimeError):
    pass


class WindowsCredentialPromptUnavailableError(RuntimeError):
    pass


CREDUIWIN_GENERIC = 0x1
ERROR_CANCELLED = 1223


def detect_current_operator() -> str:
    username = os.getenv("USERNAME") or getpass.getuser().strip()
    if not username:
        return ""

    for domain_var in ("USERDNSDOMAIN", "USERDOMAIN"):
        domain = (os.getenv(domain_var) or "").strip()
        if domain:
            return f"{domain}\\{username}"
    return username


class CREDUI_INFOW(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("hwndParent", wintypes.HWND),
        ("pszMessageText", wintypes.LPCWSTR),
        ("pszCaptionText", wintypes.LPCWSTR),
        ("hbmBanner", wintypes.HANDLE),
    ]


class WindowsCredentialPrompt:
    def _load_credui(self) -> ctypes.WinDLL:
        credui = ctypes.WinDLL("Credui", use_last_error=True)
        credui.CredUIPromptForWindowsCredentialsW.argtypes = [
            ctypes.POINTER(CREDUI_INFOW),
            wintypes.DWORD,
            ctypes.POINTER(wintypes.ULONG),
            wintypes.LPCVOID,
            wintypes.ULONG,
            ctypes.POINTER(ctypes.c_void_p),
            ctypes.POINTER(wintypes.ULONG),
            ctypes.POINTER(ctypes.c_bool),
            wintypes.DWORD,
        ]
        credui.CredUIPromptForWindowsCredentialsW.restype = wintypes.DWORD
        credui.CredUnPackAuthenticationBufferW.argtypes = [
            wintypes.DWORD,
            wintypes.LPCVOID,
            wintypes.DWORD,
            wintypes.LPWSTR,
            ctypes.POINTER(wintypes.DWORD),
            wintypes.LPWSTR,
            ctypes.POINTER(wintypes.DWORD),
            wintypes.LPWSTR,
            ctypes.POINTER(wintypes.DWORD),
        ]
        credui.CredUnPackAuthenticationBufferW.restype = wintypes.BOOL
        return credui

    def _load_advapi32(self) -> ctypes.WinDLL:
        advapi32 = ctypes.WinDLL("Advapi32", use_last_error=True)
        advapi32.CredFree.argtypes = [ctypes.c_void_p]
        advapi32.CredFree.restype = None
        return advapi32

    def prompt(self, target_name: str, message: str, caption: str = "TxTest credentials") -> WinRMCredentials:
        if sys.platform != "win32":
            raise WindowsCredentialPromptUnavailableError("Windows credential prompt is only available on Windows")

        credui = self._load_credui()
        advapi32 = self._load_advapi32()

        ui_info = CREDUI_INFOW()
        ui_info.cbSize = ctypes.sizeof(CREDUI_INFOW)
        ui_info.pszMessageText = message
        ui_info.pszCaptionText = caption

        out_auth_buffer = ctypes.c_void_p()
        out_auth_buffer_size = wintypes.ULONG()
        save = ctypes.c_bool(False)
        auth_package = wintypes.ULONG()
        result = credui.CredUIPromptForWindowsCredentialsW(
            ctypes.byref(ui_info),
            0,
            ctypes.byref(auth_package),
            None,
            0,
            ctypes.byref(out_auth_buffer),
            ctypes.byref(out_auth_buffer_size),
            ctypes.byref(save),
            CREDUIWIN_GENERIC,
        )
        if result == ERROR_CANCELLED:
            raise CredentialPromptCancelledError("Credential prompt was cancelled")
        if result != 0:
            raise RuntimeError(f"CredUIPromptForWindowsCredentialsW failed with code {result}")

        try:
            username_len = wintypes.DWORD(512)
            password_len = wintypes.DWORD(512)
            domain_len = wintypes.DWORD(512)
            username = ctypes.create_unicode_buffer(username_len.value)
            password = ctypes.create_unicode_buffer(password_len.value)
            domain = ctypes.create_unicode_buffer(domain_len.value)
            unpacked = credui.CredUnPackAuthenticationBufferW(
                0,
                out_auth_buffer,
                out_auth_buffer_size,
                username,
                ctypes.byref(username_len),
                domain,
                ctypes.byref(domain_len),
                password,
                ctypes.byref(password_len),
            )
            if not unpacked:
                raise ctypes.WinError(ctypes.get_last_error())

            resolved_username = username.value.replace("/", "\\")
            if domain.value and "\\" not in resolved_username and "@" not in resolved_username:
                resolved_username = f"{domain.value.replace('/', '\\')}\\{resolved_username}"
            return WinRMCredentials(username=resolved_username, password=password.value)
        finally:
            if out_auth_buffer.value is not None:
                advapi32.CredFree(out_auth_buffer.value)
