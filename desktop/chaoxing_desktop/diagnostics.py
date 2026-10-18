"""Offline protocol check using the same result and normalization boundary."""
from types import SimpleNamespace
from .answers import AnswerRouter
from .config import defaults, to_payload
from .query_result import query_bank
from .completion import completion_parts
from .declarative import TEMPLATE, validate_definition
import json


def offline_check():
    result = query_bank('offline', SimpleNamespace(_query=lambda q: '第二项'),
                        dict(title='离线自检', type='single', options='A.第一项\nB.第二项'))
    channel = SimpleNamespace(send=lambda *args, **kwargs: None)
    router = AnswerRouter(to_payload(defaults()), channel)
    answer = router.normalize_bank_answer(result.candidates[0].answer,
                                         dict(title='离线自检', type='single', options='A.第一项\nB.第二项'),
                                         result.review_context(result.candidates[0]))
    if result.status != 'hit' or answer != '第二项' or completion_parts('["甲","乙"]', 2) != ['甲', '乙']:
        raise ValueError('离线协议自检失败')
    validate_definition(json.dumps(TEMPLATE))
    return '离线协议自检通过：结果契约、选项定位、填空校验与 JSON 配置；未连接真实服务。'
