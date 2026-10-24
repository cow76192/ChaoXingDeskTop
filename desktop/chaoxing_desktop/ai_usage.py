"""Content-free, thread-safe accounting shared by all AI routes in one operation."""
import threading


class AIBudgetExceeded(RuntimeError):
    pass


class AIUsage:
    def __init__(self, limit=0, emit=None, token_warning=0):
        self.limit = int(limit)
        self.emit = emit
        self.lock = threading.RLock()
        self.requests = self.known = self.tokens = 0
        self.token_warning = int(token_warning)
        self.warned = False

    def snapshot(self):
        with self.lock:
            return dict(requests=self.requests, limit=self.limit, known=self.known,
                        unknown=self.requests - self.known, tokens=self.tokens)

    def publish(self):
        if self.emit:
            try:
                self.emit('ai_usage', **self.snapshot())
            except Exception:
                # Accounting transport must never discard an obtained answer.
                pass

    def reserve(self):
        with self.lock:
            if self.limit and self.requests >= self.limit:
                raise AIBudgetExceeded('本次操作 AI 请求硬上限已达到，剩余事项留待处理。')
            self.requests += 1
            self.publish()

    def record(self, body):
        usage = body.get('usage') if isinstance(body, dict) else None
        if not isinstance(usage, dict):
            return
        total = usage.get('total_tokens')
        if type(total) is not int:
            parts = (usage.get('prompt_tokens', usage.get('input_tokens')),
                     usage.get('completion_tokens', usage.get('output_tokens')))
            if not all(type(x) is int and x >= 0 for x in parts):
                return
            total = sum(parts)
        if not 0 <= total <= 10**12:
            return
        with self.lock:
            self.known += 1
            self.tokens += total
            self.publish()
            if self.token_warning and self.tokens >= self.token_warning and not self.warned:
                self.warned = True
                if self.emit:
                    try:
                        self.emit('log', level='WARNING', message='服务返回的累计 token 已达到告警值；含用量未知的请求，实际总量可能更高。告警不会中断请求，请求硬上限仍生效。')
                    except Exception:
                        pass
