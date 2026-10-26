"""Completion validation requires explicit platform blank identities."""
import json


def completion_result(answer, blank_count):
    """Return ordered parts and a diagnostic; never guess prose delimiters."""
    if type(blank_count) is not int or blank_count < 1 or blank_count > 100:
        return None, '空数未知或超出上限，缺少可核验的空位'
    if isinstance(answer, str):
        answer = answer.strip()
        parsed = None
        if answer.startswith('['):
            try:
                parsed = json.loads(answer)
            except ValueError:
                pass
        # Preserve ordinary single-blank intervals/formulas, while retaining
        # the established JSON string-array transport used by bank adapters.
        if isinstance(parsed, list) and all(isinstance(p, str) for p in parsed):
            answer = parsed
        elif blank_count == 1:
            answer = [answer]
        else:
            return None, f'预期 {blank_count} 空；来源未提供逐空数组或声明分隔规则'
    if not isinstance(answer, list):
        return None, f'预期 {blank_count} 空；答案必须为字符串数组'
    if len(answer) != blank_count:
        return None, f'预期 {blank_count} 空／返回 {len(answer)} 段'
    if not all(isinstance(part, str) and part.strip() for part in answer):
        return None, f'预期 {blank_count} 个非空字符串；返回包含空项或非文本项'
    return [part.strip() for part in answer], ''


def completion_parts(answer, blank_count):
    return completion_result(answer, blank_count)[0]


def layout_error(question):
    layout = question.get('completion_layout')
    if layout is not None and not isinstance(layout, dict):
        return '填空布局对象无效，无法序列化'
    if layout is not None and not layout.get('supported'):
        return layout.get('reason') or '填空表单结构不支持'
    count, fields = question.get('blank_count'), question.get('completion_fields')
    if fields is not None and (not isinstance(fields, list) or not all(isinstance(f, str) and f for f in fields)
                               or type(count) is not int or len(fields) != count or len(set(fields)) != count):
        return '填空表单字段与空数不符，无法序列化'
    return ''
