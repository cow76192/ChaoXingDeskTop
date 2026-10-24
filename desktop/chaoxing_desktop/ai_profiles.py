"""Named AI configuration snapshots, each sealed with Windows user DPAPI."""
import base64
import json
from pathlib import Path
import uuid

from . import credentials
from .config import defaults, validate
from .storage import revision, write_if_unchanged


class AIProfiles:
    MAX_BYTES, MAX_ROWS = 256*1024, 20

    def __init__(self, root):
        self.path = Path(root) / 'ai_profiles.json'

    def read(self):
        raw = revision(self.path)
        if raw is None:
            return [], None
        try:
            if len(raw) > self.MAX_BYTES:
                raise ValueError()
            data = json.loads(raw)
            if not isinstance(data, dict) or set(data) != {'version', 'profiles'} or data['version'] != 1:
                raise ValueError()
            rows = data['profiles']
            if not isinstance(rows, list) or len(rows) > self.MAX_ROWS:
                raise ValueError()
            ids, names = set(), set()
            for r in rows:
                if (not isinstance(r, dict) or set(r) != {'id', 'name', 'dpapi'} or
                        not isinstance(r['id'], str) or len(r['id']) != 32 or any(c not in '0123456789abcdef' for c in r['id']) or
                        not isinstance(r['name'], str) or not r['name'].strip() or len(r['name']) > 40 or
                        any(ord(c) < 32 for c in r['name']) or not isinstance(r['dpapi'], str) or not 0 < len(r['dpapi']) <= 32768 or
                        r['id'] in ids or r['name'].casefold() in names):
                    raise ValueError()
                base64.b64decode(r['dpapi'], validate=True)
                ids.add(r['id']); names.add(r['name'].casefold())
            return rows, raw
        except (ValueError, TypeError, KeyError, UnicodeError):
            raise ValueError('AI 档案损坏或容量异常；原文件保留，禁止覆盖。') from None

    def write(self, rows, expected):
        data = json.dumps(dict(version=1, profiles=rows), ensure_ascii=False).encode()
        if len(rows) > self.MAX_ROWS or len(data) > self.MAX_BYTES:
            raise ValueError('AI 档案超过 20 项 / 256 KiB 容量；原件保留。')
        write_if_unchanged(self.path, data, expected)

    def save(self, name, config):
        name = name.strip()
        if not name or len(name) > 40 or any(ord(c) < 32 for c in name):
            raise ValueError('档案名称须为 1–40 字符且不含控制字符。')
        validate(config)
        values = {k: config['ai'][k] for k in defaults()['ai']}
        body = json.dumps(values, ensure_ascii=False).encode()
        if len(body) > 16384:
            raise ValueError('AI 档案配置超过 16 KiB。')
        rows, expected = self.read()
        old = next((r for r in rows if r['name'].casefold() == name.casefold()), None)
        if old:
            self.load(old['id'])  # Never replace an unreadable credential snapshot.
        try:
            encrypted = base64.b64encode(credentials.protect(body)).decode('ascii')
        except OSError:
            raise ValueError('AI 档案加密失败，原文件未改动。') from None
        row = dict(id=old['id'] if old else uuid.uuid4().hex, name=name, dpapi=encrypted)
        self.write([row] + [r for r in rows if r['id'] != row['id']], expected)
        return row['id']

    def load(self, profile_id):
        rows, _ = self.read()
        row = next((r for r in rows if r['id'] == profile_id), None)
        if row is None:
            raise ValueError('AI 档案已变化，请重新打开列表。')
        try:
            values = json.loads(credentials.unprotect(base64.b64decode(row['dpapi'], validate=True)))
            if (not isinstance(values, dict) or set(values) != set(defaults()['ai']) or
                    any(not isinstance(v, str) for v in values.values())):
                raise ValueError()
            test = defaults(); test['ai'].update(values); validate(test)
        except (OSError, ValueError, TypeError, UnicodeError):
            raise ValueError('该 AI 档案无法在当前 Windows 用户环境解密或格式无效；当前配置和原文件保留。') from None
        return values

    def delete(self, profile_id):
        rows, expected = self.read()
        remaining = [r for r in rows if r['id'] != profile_id]
        if len(remaining) == len(rows):
            raise ValueError('AI 档案已变化，请重新打开列表。')
        self.write(remaining, expected)
