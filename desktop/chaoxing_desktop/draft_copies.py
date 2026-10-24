"""Offline human edits. No platform transport or intent-store dependency."""
import copy
import hashlib
import json
from pathlib import Path

from .activity import validate_answer
from .activity_model import valid_record as valid_activity
from .discussion_model import valid_record as valid_discussion
from .storage import revision, write_if_unchanged


def fingerprint(record):
    return hashlib.sha256(json.dumps(record, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def editable_source(kind, source):
    validator = valid_discussion if kind == 'discussion' else valid_activity if kind == 'activity' else None
    return bool(validator and validator(source) and (source['stage'] == 'draft' or
                (kind == 'activity' and source['stage'] == 'pending' and source['submit_status'] == 'draft')))


def make_copy(kind, source):
    if not editable_source(kind, source):
        raise ValueError('仅可编辑当前本地草稿；未知意图、已提交和其他状态保持只读。')
    digest = fingerprint(source)
    return dict(id=hashlib.sha256((kind + source['id'] + digest).encode()).hexdigest(), kind=kind,
                source=copy.deepcopy(source), source_hash=digest, version=0, updated='',
                content=source.get('content', ''), answers=copy.deepcopy(source.get('answers', [])))


def validate_copy(row):
    if (not isinstance(row, dict) or set(row) != {'id', 'kind', 'source', 'source_hash', 'version', 'updated', 'content', 'answers'}
            or row.get('kind') not in ('discussion', 'activity') or type(row.get('version')) is not int
            or not 0 <= row['version'] <= 10**9 or not isinstance(row['updated'], str) or len(row['updated']) > 100
            or not isinstance(row['content'], str) or len(row['content']) > 12000
            or not isinstance(row['answers'], list) or len(row['answers']) > 100):
        raise ValueError('编辑副本格式无效。')
    expected = make_copy(row['kind'], row['source'])
    if row['id'] != expected['id'] or row['source_hash'] != expected['source_hash']:
        raise ValueError('编辑副本来源变化。')
    # Invalid answers may be saved for later correction, within a bounded shape.
    for a in row['answers']:
        if (not isinstance(a, dict) or set(a) not in ({'question_id', 'text'}, {'question_id', 'option_ids'},
                {'question_id', 'text', 'source', 'valid', 'reason'}, {'question_id', 'option_ids', 'source', 'valid', 'reason'})
                or not isinstance(a.get('question_id'), str) or len(a['question_id']) > 256):
            raise ValueError('编辑答案格式无效。')
        if 'text' in a:
            if not isinstance(a['text'], str) or len(a['text']) > 12000:
                raise ValueError('文本副本超过本地编辑容量。')
        elif (not isinstance(a['option_ids'], list) or len(a['option_ids']) > 100 or
              any(not isinstance(v, str) or len(v) > 256 for v in a['option_ids'])):
            raise ValueError('选项副本格式无效。')


def constraints(row):
    """Return local errors, never claim fresh platform eligibility."""
    if row['kind'] == 'discussion':
        text = row['content']
        return [] if text.strip() and len(text) <= 1000 and not any(ord(c) < 32 and c not in '\n\t' for c in text) else ['讨论正文须非空、最多 1000 字符且无非法控制字符。']
    questions = row['source']['questions']
    answers = row['answers']
    ids = [a.get('question_id') for a in answers]
    if len(ids) != len(set(ids)) or set(ids) != {q['id'] for q in questions}:
        return ['答案必须按原生题目 ID 完整对应，不能缺题、重复或混入其他题。']
    by_id = {a['question_id']: a for a in answers}
    return [f"第 {i+1} 题：{error}" for i, q in enumerate(questions) if (error := validate_answer(q, by_id[q['id']]))]


def export_text(row):
    lines = ['人工编辑副本 v' + str(row['version']), '来源摘要：' + row['source_hash'],
             '仅本地编辑，未提交。平台限制及本人状态尚须重新核验。', row['source']['title'], '']
    if row['kind'] == 'discussion':
        lines.append(row['content'])
    else:
        answers = {a['question_id']: a for a in row['answers']}
        for q in row['source']['questions']:
            a = answers.get(q['id'], {})
            lines.extend([q['id'] + ' · ' + q['title'], a.get('text', '') if 'text' in a else
                          '\n'.join(o['text'] for o in q['options'] if o['id'] in a.get('option_ids', [])), ''])
    return '\n'.join(lines)


class DraftCopies:
    MAX_BYTES, MAX_ROWS = 2*1024*1024, 20

    def __init__(self, root, account):
        self.path = Path(root) / 'draft_copies' / (hashlib.sha256(account.encode()).hexdigest() + '.json')

    def read(self):
        raw = revision(self.path)
        if raw is None:
            return [], None
        try:
            if len(raw) > self.MAX_BYTES:
                raise ValueError()
            body = json.loads(raw)
            if not isinstance(body, dict) or set(body) != {'version', 'copies'} or body['version'] != 1:
                raise ValueError()
            rows = body['copies']
            if not isinstance(rows, list) or len(rows) > self.MAX_ROWS:
                raise ValueError()
            for row in rows:
                validate_copy(row)
            if len({r['id'] for r in rows}) != len(rows):
                raise ValueError()
            return rows, raw
        except (ValueError, TypeError, KeyError, UnicodeError):
            raise ValueError('编辑副本损坏或容量异常；原件保留，禁止覆盖。') from None

    def save(self, row):
        validate_copy(row)
        rows, expected = self.read()
        old = next((r for r in rows if r['id'] == row['id']), None)
        if (old['version'] if old else 0) != row['version']:
            raise ValueError('副本已被其他窗口修改，请重新打开。')
        updated = copy.deepcopy(row)
        updated['version'] += 1
        from datetime import datetime, timezone
        updated['updated'] = datetime.now(timezone.utc).isoformat(timespec='seconds')
        rows = [updated] + [r for r in rows if r['id'] != row['id']]
        if len(rows) > self.MAX_ROWS:
            raise ValueError('本地副本已达 20 项容量；请先导出备份，不自动淘汰人工编辑。')
        data = json.dumps(dict(version=1, copies=rows), ensure_ascii=False).encode()
        if len(data) > self.MAX_BYTES:
            raise ValueError('本地副本已达 2 MiB 容量；原件保留。')
        write_if_unchanged(self.path, data, expected)
        return updated

    def delete(self, copy_id, version):
        rows, expected = self.read()
        row = next((r for r in rows if r['id'] == copy_id), None)
        if not row or row['version'] != version:
            raise ValueError('副本已变化，请重新打开列表；未删除。')
        data = json.dumps(dict(version=1, copies=[r for r in rows if r['id'] != copy_id]), ensure_ascii=False).encode()
        write_if_unchanged(self.path, data, expected)
