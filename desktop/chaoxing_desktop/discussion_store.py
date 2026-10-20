"""Per-profile, per-account topic records. Never persist platform signatures."""
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path

from .storage import atomic_write, file_lock


def topic_key(account, course, clazz, space, topic):
    values = [str(x) for x in (account, course, clazz, space, topic)]
    if not all(values):
        raise ValueError('讨论身份不完整，禁止发布。')
    return hashlib.sha256(json.dumps(values, ensure_ascii=False).encode('utf-8')).hexdigest()


class DiscussionStore:
    MAX_BYTES = 64 * 1024
    STATES = {'draft', 'intent', 'published', 'existing', 'publish_unknown', 'rejected'}

    def __init__(self, root):
        self.root = Path(root) / 'discussions'

    def path(self, key):
        if len(key) != 64 or any(c not in '0123456789abcdef' for c in key):
            raise ValueError('讨论记录标识无效。')
        return self.root / (key + '.json')

    @contextmanager
    def locked(self, key):
        # Hold this lock across lookup/generation/POST/readback, including
        # multiple processes. No second writer can race a saved intent.
        with file_lock(self.path(key)):
            yield

    def load(self, key):
        path = self.path(key)
        if not path.exists():
            return None
        try:
            if path.stat().st_size > self.MAX_BYTES:
                raise ValueError
            record = json.loads(path.read_text(encoding='utf-8'))
            allowed = {'version', 'key', 'state', 'digest', 'level', 'content', 'reply_id', 'reason'}
            if (not isinstance(record, dict) or set(record) != allowed or record['version'] != 1
                    or record['key'] != key or record['state'] not in self.STATES
                    or not all(isinstance(record[k], str) for k in allowed - {'version'})
                    or record['level'] not in {'concise', 'medium', 'detailed', 'fixed_good'}
                    or len(record['content']) > 1000
                    or (record['state'] in {'draft', 'intent', 'publish_unknown', 'published'}
                        and not record['content'])
                    or (record['level'] == 'fixed_good' and record['content'] not in ('', '好'))):
                raise ValueError
            return record
        except (ValueError, TypeError, UnicodeError, KeyError):
            raise ValueError('讨论记录损坏，已禁止新发布；原文件已保留。') from None

    def save(self, key, *, state, digest, level, content, reply_id='', reason=''):
        if state not in self.STATES or not isinstance(content, str) or len(content) > 1000:
            raise ValueError('讨论记录内容或状态无效。')
        if level == 'fixed_good' and content not in ('', '好'):
            raise ValueError('固定回复必须恰好为好。')
        record = dict(version=1, key=key, state=state, digest=digest, level=level,
                      content=content, reply_id=str(reply_id), reason=str(reason)[:2000])
        body = json.dumps(record, ensure_ascii=False).encode('utf-8')
        if len(body) > self.MAX_BYTES:
            raise ValueError('讨论记录超过大小上限。')
        atomic_write(self.path(key), body)
        return record
