from __future__ import annotations

import base64
import ctypes
import sys
import winreg
from ctypes import POINTER, Structure, byref, c_char
from ctypes import wintypes


class DATA_BLOB(Structure):
    _fields_ = [
        ("cbData", wintypes.DWORD),
        ("pbData", POINTER(c_char)),
    ]


class WindowsProtectedStorage:
    def __init__(self, entropy: bytes) -> None:
        self._entropy = entropy
        self._crypt32 = ctypes.windll.crypt32
        self._kernel32 = ctypes.windll.kernel32

    def protect_text(self, value: str) -> str:
        encrypted = self._protect_bytes(value.encode("utf-8"))
        return base64.b64encode(encrypted).decode("ascii")

    def unprotect_text(self, value: str) -> str:
        decrypted = self._unprotect_bytes(base64.b64decode(value.encode("ascii")))
        return decrypted.decode("utf-8")

    def _protect_bytes(self, data: bytes) -> bytes:
        data_buffer = ctypes.create_string_buffer(data)
        entropy_buffer = ctypes.create_string_buffer(self._entropy)
        data_blob = DATA_BLOB(len(data), ctypes.cast(data_buffer, POINTER(c_char)))
        entropy_blob = DATA_BLOB(len(self._entropy), ctypes.cast(entropy_buffer, POINTER(c_char)))
        output_blob = DATA_BLOB()

        if not self._crypt32.CryptProtectData(
            byref(data_blob),
            None,
            byref(entropy_blob),
            None,
            None,
            0,
            byref(output_blob),
        ):
            raise OSError("Unable to protect local license data.")

        try:
            return ctypes.string_at(output_blob.pbData, output_blob.cbData)
        finally:
            self._kernel32.LocalFree(output_blob.pbData)

    def _unprotect_bytes(self, data: bytes) -> bytes:
        data_buffer = ctypes.create_string_buffer(data)
        entropy_buffer = ctypes.create_string_buffer(self._entropy)
        data_blob = DATA_BLOB(len(data), ctypes.cast(data_buffer, POINTER(c_char)))
        entropy_blob = DATA_BLOB(len(self._entropy), ctypes.cast(entropy_buffer, POINTER(c_char)))
        output_blob = DATA_BLOB()

        if not self._crypt32.CryptUnprotectData(
            byref(data_blob),
            None,
            byref(entropy_blob),
            None,
            None,
            0,
            byref(output_blob),
        ):
            raise ValueError("Local license data could not be decrypted.")

        try:
            return ctypes.string_at(output_blob.pbData, output_blob.cbData)
        finally:
            self._kernel32.LocalFree(output_blob.pbData)


class WindowsRegistryStore:
    def __init__(self, registry_path: str) -> None:
        self._registry_path = registry_path

    def write_text(self, name: str, value: str) -> None:
        try:
            with winreg.CreateKey(winreg.HKEY_CURRENT_USER, self._registry_path) as key:
                winreg.SetValueEx(key, name, 0, winreg.REG_SZ, value)
        except OSError:
            return

    def read_text(self, name: str) -> str | None:
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, self._registry_path) as key:
                value, _value_type = winreg.QueryValueEx(key, name)
        except OSError:
            return None
        return value or None


class WindowsRuntimeGuard:
    @staticmethod
    def debugger_attached() -> bool:
        if sys.gettrace() is not None:
            return True

        kernel32 = ctypes.windll.kernel32
        if kernel32.IsDebuggerPresent():
            return True

        debug_flag = wintypes.BOOL()
        process_handle = kernel32.GetCurrentProcess()
        if kernel32.CheckRemoteDebuggerPresent(process_handle, byref(debug_flag)) and debug_flag.value:
            return True
        return False
