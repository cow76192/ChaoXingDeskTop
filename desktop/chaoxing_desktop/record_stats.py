"""Small incremental summaries, updated only when a retained record changes."""
from collections import Counter


class RecordStats:
    def __init__(self):
        self.stages = Counter()
        self.sources = Counter()
        self.confirmed = 0

    def add(self, record, direction=1):
        self.stages[record['stage']] += direction
        self.confirmed += direction * (record['task_status'] == 'confirmed')
        for answer in record.get('answers', ()):
            if answer['valid']:
                self.sources[answer['source']] += direction
