"""Current Windows user's DPAPI protection; never fall back to plaintext."""
from __future__ import annotations

import ctypes
from ctypes import wintypes
import os


class DataBlob(ctypes.Structure):
    _fields_ = [("size", wintypes.DWORD), ("data", ctypes.POINTER(ctypes.c_ubyte))]


def _crypt(data: bytes, decrypt: bool) -> bytes:
    if os.name != "nt":
        raise OSError("本机凭据加密需要 Windows。")
    crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    blob_pointer = ctypes.POINTER(DataBlob)
    protect = crypt32.CryptProtectData
    protect.argtypes = [blob_pointer, wintypes.LPCWSTR, blob_pointer, ctypes.c_void_p,
                        ctypes.c_void_p, wintypes.DWORD, blob_pointer]
    protect.restype = wintypes.BOOL
    unprotect = crypt32.CryptUnprotectData
    unprotect.argtypes = [blob_pointer, ctypes.c_void_p, blob_pointer, ctypes.c_void_p,
                          ctypes.c_void_p, wintypes.DWORD, blob_pointer]
    unprotect.restype = wintypes.BOOL
    free = kernel32.LocalFree
    free.argtypes = [ctypes.c_void_p]
    free.restype = ctypes.c_void_p
    buffer = ctypes.create_string_buffer(data)
    source = DataBlob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)))
    result = DataBlob()
    # UI_FORBIDDEN (1), with no LOCAL_MACHINE flag: bind to the current user.
    if decrypt:
        ok = unprotect(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(result))
    else:
        ok = protect(ctypes.byref(source), "ChaoxingDesktop service credentials", None,
                     None, None, 1, ctypes.byref(result))
    if not ok:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        return ctypes.string_at(result.data, result.size)
    finally:
        if decrypt:
            ctypes.memset(result.data, 0, result.size)
        free(ctypes.cast(result.data, ctypes.c_void_p))
        ctypes.memset(buffer, 0, len(buffer))


def protect(data: bytes) -> bytes:
    return _crypt(data, decrypt=False)


def unprotect(data: bytes) -> bytes:
    return _crypt(data, decrypt=True)
