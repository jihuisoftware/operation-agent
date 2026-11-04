"""User-facing failures after the shared model runtime exhausts its retry/fallback ladder."""
import httpx
from openai import APIConnectionError


class ModelServiceUnavailable(RuntimeError):
    """Partial business results remain usable while the provider is unavailable."""


def service_failure(error):
    status = getattr(error, 'status_code', None)
    messages = {
        408: '模型请求超时（408）',
        429: '模型服务限流或额度不足（429）',
        500: '模型服务内部错误（500）',
        502: '模型服务网关异常（502）',
        503: '模型服务繁忙（503）',
        504: '模型服务响应超时（504）',
    }
    message = messages.get(status)
    if not message and isinstance(error, (APIConnectionError, httpx.TransportError, TimeoutError, ConnectionError)):
        message = '模型服务连接失败或超时'
    if not message:
        return None
    return ModelServiceUnavailable(message + '；当前调用未成功，已保留完成的结果。请稍后重试，或在设置中检查/切换模型。')
