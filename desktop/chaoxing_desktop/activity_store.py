"""Durable activity drafts and write intents, isolated by native identity."""
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path

from .storage import atomic_write, file_lock


def activity_key(account, course, clazz, namespace, activity):
    values = [str(x) for x in (account, course, clazz, namespace, activity)]
    if not all(values):
        raise ValueError('活动身份不完整，禁止提交。')
    return hashlib.sha256(json.dumps(values, ensure_ascii=False).encode()).hexdigest()


def valid_answers(answers):
    if not isinstance(answers, list) or len(answers) > 100:
        return False
    ids = set()
    for answer in answers:
        if not isinstance(answer, dict) or set(answer) not in (
                {'question_id', 'option_ids', 'source', 'valid', 'reason'},
                {'question_id', 'text', 'source', 'valid', 'reason'}):
            return False
        qid = answer['question_id']
        if (not isinstance(qid, str) or not 0 < len(qid) <= 256 or qid in ids
                or answer['source'] not in ('ai', 'random', 'fixed', '')
                or type(answer['valid']) is not bool
                or not isinstance(answer['reason'], str) or len(answer['reason']) > 2000):
            return False
        ids.add(qid)
        if 'text' in answer:
            if not isinstance(answer['text'], str) or len(answer['text']) > 1000:
                return False
            if answer['source'] == 'fixed' and answer['text'] != '好':
                return False
        else:
            options = answer['option_ids']
            if (not isinstance(options, list) or len(options) > 100
                    or not all(isinstance(x, str) and 0 < len(x) <= 256 for x in options)
                    or len(set(options)) != len(options) or answer['source'] == 'fixed'):
                return False
    return True


class ActivityStore:
    MAX_BYTES = 512 * 1024
    MAX_TOTAL = 64 * 1024 * 1024
    STATES = {'draft', 'intent', 'submitted', 'existing', 'submit_unknown', 'rejected'}

    def __init__(self, root):
        self.root = Path(root) / 'activities'

    def path(self, key):
        if not isinstance(key, str) or len(key) != 64 or any(c not in '0123456789abcdef' for c in key):
            raise ValueError('活动记录标识无效。')
        return self.root / (key + '.json')

    @contextmanager
    def locked(self, key):
        with file_lock(self.path(key)):
            yield

    def load(self, key):
        path = self.path(key)
        if not path.exists():
            return None
        try:
            if path.stat().st_size > self.MAX_BYTES:
                raise ValueError
            r = json.loads(path.read_text(encoding='utf-8'))
            fields = {'version', 'key', 'state', 'digest', 'strategy', 'answers', 'receipt', 'reason'}
            if (not isinstance(r, dict) or set(r) != fields or r['version'] != 1 or r['key'] != key
                    or r['state'] not in self.STATES or not valid_answers(r['answers'])
                    or not all(isinstance(r[k], str) and len(r[k]) <= 2000
                               for k in ('digest', 'strategy', 'receipt', 'reason'))
                    or (r['state'] in ('intent', 'submitted', 'submit_unknown') and not r['answers'])):
                raise ValueError
            return r
        except (ValueError, TypeError, KeyError, UnicodeError):
            raise ValueError('活动记录损坏，原文件已保留，禁止新提交。') from None

    def save(self, key, *, state, digest, strategy, answers, receipt='', reason=''):
        if (state not in self.STATES or not valid_answers(answers)
                or (state in ('intent', 'submitted', 'submit_unknown') and not answers)):
            raise ValueError('活动记录状态或逐题答案无效。')
        record = dict(version=1, key=key, state=state, digest=str(digest), strategy=str(strategy),
                      answers=answers, receipt=str(receipt)[:2000], reason=str(reason)[:2000])
        body = json.dumps(record, ensure_ascii=False).encode('utf-8')
        if len(body) > self.MAX_BYTES:
            raise ValueError('活动草稿超过 512 KiB 上限。')
        path = self.path(key)
        # Fail closed on capacity exhaustion; never delete unresolved intents.
        with file_lock(self.root / 'capacity'):
            total = sum(p.stat().st_size for p in self.root.glob('*.json') if p != path)
            if total + len(body) > self.MAX_TOTAL:
                raise ValueError('活动存储容量已达上限，未清除任何草稿或提交意图。')
            atomic_write(path, body)
        return record
