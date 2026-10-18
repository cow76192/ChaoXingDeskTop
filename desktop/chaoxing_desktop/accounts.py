"""Independent local account profiles and DPAPI-protected session cookies."""
from __future__ import annotations

import json
from pathlib import Path
import re
import uuid

from . import credentials
from .storage import atomic_write, file_lock, revision


def parse_cookie(text: str) -> dict[str, str]:
    items = [item.strip() for item in text.strip().split(";") if item.strip()]
    if not items or any("=" not in item or not item.split("=", 1)[0].strip() for item in items):
        raise ValueError("Cookie 应为 name=value; name=value 格式。")
    return dict(item.split("=", 1) for item in items)


def cookie_uid(cookies: dict) -> str:
    return str(cookies.get("_uid") or cookies.get("UID") or "")


def read_cookie(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    return parse_cookie(credentials.unprotect(path.read_bytes()).decode("utf-8"))


def write_cookie(path: Path, cookies: dict, expected_uid=""):
    if expected_uid and cookie_uid(cookies) != expected_uid:
        raise ValueError("会话所属用户与当前账号不一致，请添加为其他账号。")
    text = "; ".join(f"{key}={value}" for key, value in cookies.items())
    parse_cookie(text)
    atomic_write(path, credentials.protect(text.encode("utf-8")))


class AccountStore:
    def __init__(self, root: Path):
        self.root = root
        self.path = root / "accounts.json"
        self.rows = []
        self.active = ""
        self._revision = revision(self.path)
        if self.path.exists():
            value = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(value, dict) or value.get("version") != 1 or not isinstance(value.get("accounts"), list):
                raise ValueError("账号文件格式无效或来自更新版本，原文件已保留。")
            seen = set()
            for row in value["accounts"]:
                if (not isinstance(row, dict) or any(not isinstance(row.get(k), str) for k in ("id", "username", "label", "uid"))
                        or not re.fullmatch(r"[0-9a-f]{32}", row["id"]) or row["id"] in seen):
                    raise ValueError("账号文件内容无效，原文件已保留。")
                seen.add(row["id"])
            if value.get("active", "") not in seen | {""}:
                raise ValueError("当前账号标识无效，原文件已保留。")
            self.rows = value["accounts"]
            self.active = value.get("active", "")

    def get(self, account_id):
        return next((row for row in self.rows if row["id"] == account_id), None)

    def cookie_path(self, account_id):
        if not re.fullmatch(r"[0-9a-f]{32}", account_id):
            raise ValueError("账号标识无效。")
        return self.root / "accounts" / account_id / "cookies.dat"

    def commit(self, rows, active):
        with file_lock(self.path):
            self._commit_locked(rows, active)

    def _check_revision(self):
        if revision(self.path) != self._revision:
            raise ValueError('账号已被另一个实例修改，原文件已保留。请重新打开程序。')

    def _commit_locked(self, rows, active):
        self._check_revision()
        content = json.dumps(dict(version=1, active=active, accounts=rows), ensure_ascii=False, indent=2).encode('utf-8')
        atomic_write(self.path, content)
        self._revision = content
        self.rows, self.active = rows, active

    def add(self, username, label=""):
        if username and any(row["username"] == username for row in self.rows):
            raise ValueError("该账号已存在，请从已保存账号中切换。")
        row = dict(id=uuid.uuid4().hex, username=username, label=label or username or "Cookie 账号", uid="")
        self.commit(self.rows + [row], row["id"])
        return row

    def update(self, account_id, **values):
        if not self.get(account_id):
            raise ValueError("账号不存在。")
        self.commit([dict(row, **values) if row["id"] == account_id else row for row in self.rows], self.active)

    def migrate(self, username):
        if self.path.exists():
            return
        legacy = self.root / "cookies.txt"
        if username or legacy.exists():
            cookies = parse_cookie(legacy.read_text(encoding="utf-8-sig")) if legacy.exists() else None
            row = dict(id=uuid.uuid4().hex, username=username, label=username or "原有 Cookie 账号",
                       uid=cookie_uid(cookies or {}))
            if cookies:
                write_cookie(self.cookie_path(row["id"]), cookies)
            self.commit([row], row["id"])
            if cookies:
                legacy.unlink()

    def remove(self, account_id):
        if not self.get(account_id):
            return
        with file_lock(self.path):
            self._check_revision()  # Do not delete a secret from stale account state.
            path = self.cookie_path(account_id)
            previous = revision(path)
            path.unlink(missing_ok=True)
            try:
                self._commit_locked([row for row in self.rows if row['id'] != account_id],
                                    '' if self.active == account_id else self.active)
            except Exception:
                if previous is not None:
                    atomic_write(path, previous)
                raise
