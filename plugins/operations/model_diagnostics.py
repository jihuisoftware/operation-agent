"""Bounded, redacted local response evidence; never retain requests or reasoning here."""
import hashlib

from hermes_cli.debug_redaction import redact_debug_support_text

MAX_EVIDENCE_CHARS = 16384
MAX_REDACTION_CHARS = 131072


def response_evidence(response):
    choices = getattr(response, 'choices', None)
    choice = choices[0] if isinstance(choices, (list, tuple)) and choices else None
    raw = getattr(getattr(choice, 'message', None), 'content', None)
    reason = getattr(choice, 'finish_reason', None)
    result = {'finish_reason': redact_debug_support_text(reason, max_chars=100) if reason is not None else None,
              'raw_response': None, 'response_chars': len(raw) if isinstance(raw, str) else None,
              'response_truncated': False, 'response_redacted': False}
    if not isinstance(raw, str):
        result['response_evidence_omitted'] = 'non_text'
        return result
    result['response_sha256'] = hashlib.sha256(raw.encode('utf-8', errors='surrogatepass')).hexdigest()
    if len(raw) > MAX_REDACTION_CHARS:
        result.update(response_truncated=True, response_evidence_omitted='oversized')
        return result
    safe = redact_debug_support_text(raw)
    result['response_redacted'] = safe != raw
    if len(safe) > MAX_EVIDENCE_CHARS:
        safe = safe[:12288] + '\n[中间响应已截断]\n' + safe[-4096:]
        result['response_truncated'] = True
    result['raw_response'] = safe
    return result


def record_failure(store, budget_id, error):
    from .model_trace import update
    diagnostic = error.diagnostics
    store.event('model_output_error', {'budget_id': budget_id, 'error': str(error), **diagnostic})
    store.progress('模型输出解析失败', {'budget_id': budget_id, 'error': str(error),
                                    **{key: value for key, value in diagnostic.items() if key != 'raw_response'}})
    if getattr(store, 'debug_id', None):
        update(store, 'model-trace:' + budget_id, {'diagnostics': diagnostic})
