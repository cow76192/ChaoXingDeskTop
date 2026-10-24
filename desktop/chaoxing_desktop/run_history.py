"""Bounded local summaries. Never a source for replay or submission decisions."""
import hashlib
import json
from pathlib import Path

from .storage import revision, write_if_unchanged


class RunHistory:
    MAX_BYTES = 2 * 1024 * 1024
    MAX_RUNS = 20

    def __init__(self, root, account):
        self.path = Path(root) / 'run_summaries' / (hashlib.sha256(account.encode()).hexdigest() + '.json')

    @staticmethod
    def validate_run(run):
        if (not isinstance(run, dict) or not all(isinstance(run.get(k), str) and len(run[k]) <= 200 for k in ('id', 'time', 'state'))
                or not run['id'] or not isinstance(run.get('counts'), dict) or len(run['counts']) > 20
                or not isinstance(run.get('tasks'), list) or len(run['tasks']) > 1000):
            raise ValueError()
        if any(type(v) is not int or not 0 <= v <= 10**9 for v in run['counts'].values()):
            raise ValueError()
        for key in ('total', 'retained'):
            if key in run and (type(run[key]) is not int or not 0 <= run[key] <= 10**9):
                raise ValueError()
        if 'policy' in run and (not isinstance(run['policy'], str) or len(run['policy']) > 65536):
            raise ValueError()
        if 'ai' in run and (not isinstance(run['ai'], dict) or len(run['ai']) > 20 or
                           any(type(v) is not int or not 0 <= v <= 10**15 for v in run['ai'].values())):
            raise ValueError()
        courses = run.get('courses', [])
        if not isinstance(courses, list) or len(courses) > 1000:
            raise ValueError()
        for row, required in [(t, ('title', 'course', 'status')) for t in run['tasks']] + [(c, ('title',)) for c in courses]:
            if (not isinstance(row, dict) or any(not isinstance(row.get(k), str) or len(row[k]) > 200 for k in required)
                    or any(not isinstance(row[k], str) or not 0 < len(row[k]) <= 256
                           for k in ('courseId', 'clazzId', 'pointId') if k in row)):
                raise ValueError()

    def read(self):
        raw = revision(self.path)
        if raw is None:
            return [], None
        if len(raw) > self.MAX_BYTES:
            raise ValueError('运行摘要容量异常，原文件保留。')
        try:
            data = json.loads(raw)
            if (type(data) is not dict or data.get('version') != 1 or not isinstance(data.get('runs'), list)
                    or len(data['runs']) > self.MAX_RUNS):
                raise ValueError()
            for run in data['runs']:
                self.validate_run(run)
            if len({run['id'] for run in data['runs']}) != len(data['runs']):
                raise ValueError()
            return data['runs'], raw
        except (ValueError, TypeError, UnicodeError):
            raise ValueError('运行摘要损坏或格式未知，原文件保留；请备份后单独处理该摘要文件。') from None

    def save(self, summary):
        self.validate_run(summary)
        rows, expected = self.read()
        rows = [summary] + [row for row in rows if row['id'] != summary['id']]
        rows = rows[:self.MAX_RUNS]
        while True:
            body = json.dumps(dict(version=1, runs=rows), ensure_ascii=False).encode('utf-8')
            if len(body) <= self.MAX_BYTES:
                break
            if len(rows) <= 1:
                raise ValueError('本轮摘要超过容量，原文件保留。')
            rows.pop()
        write_if_unchanged(self.path, body, expected)
