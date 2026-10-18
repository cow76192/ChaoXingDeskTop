"""Per-service connection pools with bounded response bodies and read deadlines."""
import threading
import time
import requests
from .control import checkpoint


def service_request(owner, method, url, max_bytes=2*1024*1024, **kwargs):
    local = vars(owner).setdefault('_http_local', threading.local())
    if not hasattr(local, 'session'):
        local.session = requests.Session()  # No platform Cookie/header inheritance.
    kwargs.setdefault('allow_redirects', False)
    kwargs.setdefault('timeout', (10, 30))
    timeout = kwargs['timeout']
    read_timeout = timeout[-1] if isinstance(timeout, tuple) else timeout
    deadline = min(vars(owner).get('_http_deadline', float('inf')), time.monotonic() + float(read_timeout) + 10)
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise requests.Timeout('本次查询已超过总耗时预算')
    kwargs['timeout'] = (min(10, remaining), min(float(read_timeout), remaining))
    kwargs['stream'] = True
    checkpoint(owner)
    response = getattr(local.session, method)(url, **kwargs)
    return read_response(response, owner, deadline, max_bytes)


def read_response(response, owner, deadline, max_bytes):
    # Buffered third-party response doubles need no socket draining. Actual
    # requests responses are consumed here, before callers can call .json().
    if not isinstance(response, requests.Response):
        return response
    try:
        length = response.headers.get('Content-Length', '')
        if length.isdigit() and int(length) > max_bytes:
            raise ValueError('服务响应超过大小上限')
        parts, size = [], 0
        for chunk in response.iter_content(8192):
            checkpoint(owner, cancel_only=True)
            if time.monotonic() > deadline:
                raise requests.Timeout('服务响应超过总读取时间预算')
            size += len(chunk)
            if size > max_bytes:
                raise ValueError('服务响应超过大小上限')
            parts.append(chunk)
        response._content = b''.join(parts)
        response._content_consumed = True
        return response
    finally:
        response.close()


def platform_request(session, request, *args, **kwargs):
    kwargs.setdefault('timeout', 5)
    kwargs.setdefault('stream', True)
    timeout = kwargs['timeout']
    seconds = timeout[-1] if isinstance(timeout, tuple) else timeout
    checkpoint(session)
    response = request(*args, **kwargs)
    return read_response(response, session, time.monotonic() + float(seconds) + 10, 8*1024*1024)
