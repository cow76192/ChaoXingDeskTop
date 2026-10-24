"""Data-only HTTP JSON adapters. No eval, expressions or downloaded code."""
import copy
import json
import re
from urllib.parse import urlparse

TEMPLATE = dict(version=1, name='我的 JSON 题库', url='https://example.test/query', method='POST',
                headers={'Authorization': 'Bearer ${token}'},
                data={'question': '${title}', 'options': '${options}', 'type': '${type}'},
                results_path='data', answer_path='answer', title_path='question', options_path='options',
                type_map={})
KEYS = set(TEMPLATE)
ENV_KEYS = {'title', 'options', 'type', 'token'}


def preview_definition(text):
    """Describe routing/mapping without exposing literal header or data values."""
    if len(text.encode('utf-8')) > 65536:
        raise ValueError('题库定义超过 64 KiB')
    raw = json.loads(text)
    if not isinstance(raw, dict):
        raise ValueError('题库定义必须为 JSON 对象')
    rejected = sorted(set(raw) - KEYS)
    try:
        definition = validate_definition(text)
        error = ''
    except (ValueError, TypeError, AttributeError) as exc:
        definition, error = None, str(exc)
    address = raw.get('url', '')
    try:
        domain = urlparse(address).hostname or '无法识别'
    except (ValueError, TypeError, AttributeError):
        domain = '无法识别'
    lines = ['仅导入配置，不联网。Token 仍需单独填写。', '目标域名：' + domain,
             '方法：' + str(raw.get('method', '未指定'))[:30],
             '请求映射（固定值不展示）：']
    for kind in ('headers', 'data'):
        items = raw.get(kind, {})
        if isinstance(items, dict):
            for key, value in list(items.items())[:24]:
                variables = re.findall(r'\$\{(title|options|type|token)\}', value) if isinstance(value, str) else []
                lines.append(kind + '[' + str(key)[:80] + '] ← ' + (', '.join(variables) or '固定值 / 非法结构'))
    lines.append('响应映射：')
    for key in ('results_path', 'answer_path', 'title_path', 'options_path', 'type_map'):
        lines.append(key + ' ← ' + json.dumps(raw.get(key, ''), ensure_ascii=False)[:400])
    lines.append('拒绝的脚本／扩展字段：' + (', '.join(k[:80] for k in rejected[:24]) or '无'))
    lines.append('校验：' + (error if error else '通过；确认后替换当前声明式定义。'))
    return definition, '\n'.join(lines)


def path_value(value, path):
    if not path:
        return value
    for part in path.split('.'):
        if not isinstance(value, dict):
            raise ValueError('响应字段路径不存在')
        value = value[part]
    return value


def validate_definition(text):
    if len(text) > 65536:
        raise ValueError('题库定义超过 64 KiB')
    definition = json.loads(text)
    if not isinstance(definition, dict):
        raise ValueError('题库定义必须为 JSON 对象')
    extra = set(definition) - KEYS
    if extra:
        raise ValueError('不支持的题库字段（不执行 handler）：' + ', '.join(sorted(extra)))
    if definition.get('version') != 1 or definition.get('method') not in ('GET', 'POST'):
        raise ValueError('题库格式版本必须为 1，请求方法为 GET 或 POST')
    url = urlparse(definition.get('url', ''))
    if url.scheme not in ('http', 'https') or not url.hostname or url.username or url.password or url.fragment:
        raise ValueError('题库 URL 必须是无内嵌凭据的 HTTP(S) 地址')
    if url.query:
        raise ValueError('查询参数请放入 data；凭据只使用独立 Token')
    for key in ('results_path', 'answer_path', 'title_path', 'options_path'):
        path = definition.get(key, '')
        if not isinstance(path, str) or len(path) > 200 or (path and not re.fullmatch(r'[A-Za-z0-9_-]+(?:\.[A-Za-z0-9_-]+)*', path)):
            raise ValueError('响应路径仅支持以点分隔的字段名')
    if not definition.get('answer_path'):
        raise ValueError('需要指定 answer_path')
    if not isinstance(definition.get('name', ''), str) or len(definition.get('name', '')) > 80:
        raise ValueError('题库名称无效')
    mapping = definition.get('type_map', {})
    if not isinstance(mapping, dict) or any(k not in ('single', 'multiple', 'judgement', 'completion', 'shortanswer') or type(v) not in (str, int) for k, v in mapping.items()):
        raise ValueError('题型映射无效')
    for key in ('headers', 'data'):
        items = definition.get(key, {})
        if not isinstance(items, dict) or len(items) > 24:
            raise ValueError('headers/data 必须为有限的字段对象')
        for name, value in items.items():
            if not re.fullmatch(r'[A-Za-z0-9_-]{1,80}', name) or not isinstance(value, str) or len(value) > 4000:
                raise ValueError('模板仅支持字段名和字符串值，不支持脚本或嵌套对象')
            if key == 'headers' and name.lower() in ('cookie', 'host', 'proxy-authorization', 'content-length'):
                raise ValueError('不允许设置会话或传输控制请求头')
            if '${' in value and (any(p not in ENV_KEYS for p in re.findall(r'\$\{([^}]+)\}', value)) or '${' in re.sub(r'\$\{(?:title|options|type|token)\}', '', value)):
                raise ValueError('未知模板变量或表达式；仅支持 title/options/type/token')
            if key == 'headers' and ('\n' in value or '\r' in value):
                raise ValueError('请求头不能含换行')
            if any(s in name.lower() for s in ('authorization', 'key', 'token', 'secret')) and '${token}' not in value:
                raise ValueError('凭据字段必须引用 ${token}，请在独立 Token 输入框填写凭据')
    return definition


def expand(items, env):
    return {key: re.sub(r'\$\{([^}]+)\}', lambda m: str(env[m[1]]), value) for key, value in items.items()}


class DeclarativeBank:
    DISABLE = False

    def __init__(self, config):
        self._conf = config
        self.definition = validate_definition(config['declarative_definition'])
        self.name = self.definition.get('name') or '声明式 JSON 题库'
        self.api = self.definition['url']
        self.last_candidates = []
        self._last_query_request = None

    def _query(self, question):
        # Reuse native HTTP retry/timeout/budget without inheriting platform sessions.
        from api.answer import Tiku
        self.last_candidates = []
        env = dict(title=question.get('title', ''), options=question.get('options', ''),
                   type=self.definition.get('type_map', {}).get(question.get('type'), question.get('type', 'unknown')),
                   token=self._conf.get('declarative_token', ''))
        headers = expand(self.definition.get('headers', {}), env)
        data = expand(self.definition.get('data', {}), env)
        if self.definition['method'] == 'POST':
            response = Tiku.request(self, 'post', json=data, headers=headers, allow_redirects=False)
        else:
            response = Tiku.request(self, 'get', params=data, headers=headers, allow_redirects=False)
        if response.status_code != 200:
            self.last_query_status = 'error'
            return None
        body = response.json()
        rows = path_value(body, self.definition.get('results_path', ''))
        if rows is None or rows == []:
            self.last_query_status = 'miss'
            return None
        if isinstance(rows, dict):
            rows = [rows]
        if not isinstance(rows, list) or len(rows) > 100:
            raise ValueError('候选答案格式错误')
        from .query_result import AnswerCandidate
        for row in rows:
            answer = path_value(row, self.definition['answer_path'])
            if isinstance(answer, list) and all(isinstance(x, str) for x in answer):
                answer = json.dumps(answer, ensure_ascii=False) if question.get('type') == 'completion' else '\n'.join(answer)
            if not isinstance(answer, str):
                raise ValueError('答案必须为字符串或字符串数组')
            if answer.strip():
                title = path_value(row, self.definition['title_path']) if self.definition.get('title_path') else ''
                options = path_value(row, self.definition['options_path']) if self.definition.get('options_path') else None
                if not isinstance(title, str):
                    raise ValueError('候选题干必须为字符串')
                self.last_candidates.append(AnswerCandidate(answer, title, copy.deepcopy(options)))
        return self.last_candidates[0].answer if self.last_candidates else None

    def _wait_for_query_request(self):
        from api.answer import Tiku
        return Tiku._wait_for_query_request(self)

    def _before_request(self):
        from api.answer import Tiku
        return Tiku._before_request(self)

    def _observe_response(self, response):
        from api.answer import Tiku
        return Tiku._observe_response(self, response)
