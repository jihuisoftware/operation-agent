"""Decode only the received model output; transport and policy failures stay distinct."""
import json

from .model_errors import ModelOutputError


def decode(response):
    choices = getattr(response, 'choices', None)
    message = getattr(choices[0], 'message', None) if isinstance(choices, (list, tuple)) and choices else None
    raw = getattr(message, 'content', None)
    if not isinstance(raw, str):
        raise ModelOutputError('模型没有返回有效文本结果')
    raw = raw.strip()
    if raw.startswith('```'):
        _, separator, body = raw.partition('\n')
        if not separator:
            raise ModelOutputError('模型返回的代码块缺少JSON正文')
        raw = body.rsplit('```', 1)[0]
    try:
        result = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ModelOutputError('模型返回的JSON格式无效，本次结果未采用') from exc
    if not isinstance(result, dict):
        raise ModelOutputError('模型没有返回有效结构化结果')
    return result
