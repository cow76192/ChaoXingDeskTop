# -*- coding: utf-8 -*-
import os.path
from pathlib import Path
import threading

import requests

from api.config import GlobalConst as gc

# 定义全局 Cookie 文件锁，保证读写绝对安全
cookie_lock = threading.RLock()
_expected_uid = ""
_load_existing = True


def configure_account(path, expected_uid="", load_existing=True):
    """Called once by the isolated desktop worker, before creating a session."""
    global _expected_uid, _load_existing
    gc.COOKIES_PATH = str(path)
    _expected_uid = expected_uid
    _load_existing = load_existing


def save_cookies(session: requests.Session):
    global _load_existing
    with cookie_lock:
        if str(gc.COOKIES_PATH).endswith('.dat'):
            from chaoxing_desktop.accounts import write_cookie
            write_cookie(Path(gc.COOKIES_PATH), session.cookies.get_dict(), _expected_uid)
            _load_existing = True
            return
        buffer = ""
        for k, v in session.cookies.items():
            buffer += f"{k}={v};"
        buffer = buffer.removesuffix(";")
        with open(gc.COOKIES_PATH, "w") as f:
            f.write(buffer)


def use_cookies() -> dict:
    with cookie_lock:
        if not _load_existing:
            return {}
        if str(gc.COOKIES_PATH).endswith('.dat'):
            from chaoxing_desktop.accounts import read_cookie
            # A damaged protected session is actionable; never hide decryption errors.
            return read_cookie(Path(gc.COOKIES_PATH))
        if not os.path.exists(gc.COOKIES_PATH):
            return {}

        cookies = {}
        try:
            with open(gc.COOKIES_PATH, "r") as f:
                buffer = f.read().strip()
                if not buffer:
                    return {}
                for item in buffer.split(";"):
                    item = item.strip()
                    if not item:
                        continue
                    parts = item.split("=", 1)
                    if len(parts) == 2:
                        cookies[parts[0]] = parts[1]
        except Exception:
            return {}

        return cookies
