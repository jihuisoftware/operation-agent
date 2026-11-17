"""Decode only the received model output; transport and policy failures stay distinct."""
import json

from .model_errors import ModelOutputError
from .model_diagnostics import response_evidence


def failure(response, message, *, parse_error=None):
    diagnostics = response_evidence(response)
    if parse_error is not None:
        diagnostics['parse_error'] = parse_error
    return ModelOutputError(message, diagnostics=diagnostics)


def decode(response):
    choices = getattr(response, 'choices', None)
    message = getattr(choices[0], 'message', None) if isinstance(choices, (list, tuple)) and choices else None
    raw = getattr(message, 'content', None)
    if not isinstance(raw, str):
        raise failure(response, '模型没有返回有效文本结果')
    original = raw
    offset = len(raw) - len(raw.lstrip())
    raw = raw.strip()
    if raw.startswith('```'):
        _, separator, body = raw.partition('\n')
        if not separator:
            raise failure(response, '模型返回的代码块缺少JSON正文')
        offset += raw.index('\n') + 1
        raw = body.rsplit('```', 1)[0]
    try:
        result = json.loads(raw)
    except json.JSONDecodeError as exc:
        position = offset + exc.pos
        details = {'message': exc.msg, 'line': exc.lineno, 'column': exc.colno, 'offset': exc.pos,
                   'raw_offset': position, 'raw_line': original.count('\n', 0, position) + 1,
                   'raw_column': position - original.rfind('\n', 0, position)}
        raise failure(response, f'模型返回的JSON格式无效（第{exc.lineno}行，第{exc.colno}列），本次结果未采用',
                      parse_error=details) from exc
    if not isinstance(result, dict):
        raise failure(response, '模型没有返回有效结构化结果')
    return result
