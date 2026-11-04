"""Read-only end-to-end browser diagnosis; never generate content or submit platform actions."""
import re

from fastapi import HTTPException

from plugins.operations.store import Store


def check(body):
    from .operations_debug import require_enabled
    from plugins.operations.workflow import browser
    require_enabled()
    request = body.get('request_id')
    if not isinstance(request, str) or not re.fullmatch(r'[a-zA-Z0-9_-]{1,100}', request):
        raise HTTPException(400, '检查请求标识无效')
    store = Store()
    version, policy = store.policy()
    if body.get('version') != version or not policy['enabled'] or policy['paused']:
        raise HTTPException(409, '请确认计划已启用并刷新规则')
    token = 'browser-check:' + request
    if not store.lease(token):
        raise HTTPException(409, '已有任务执行中，本次只读检查未开始')
    try:
        from plugins.operations.readiness import web_block_reason
        with store.connection() as db:
            held = web_block_reason(db)
        if held:
            raise HTTPException(409, held)
        result = browser(store, 'account', {'resume_probe': True, 'readonly_inventory': 'comment',
                                         'keywords': policy['keywords']})
        if result.get('probe') != 'account_and_search' or result.get('state') != 'logged_in':
            raise HTTPException(409, '当前桌面尚未完成搜索页检查，请刷新应用后重试')
        expected = policy['account_id']
        if not expected and store.workspace:
            from plugins.operations.execution_pause import account_key
            with store.connection() as db:
                expected = db.execute('SELECT identity FROM directory.accounts WHERE id=?', (account_key(store, db),)).fetchone()[0]
        if expected and expected != result.get('account_id'):
            raise HTTPException(409, '当前登录账号与主题关联账号不匹配')
        return {'state': 'completed', 'detail': f"账号已核对，搜索页读取成功，取得 {len(result.get('items', []))} 个候选；未调用模型或提交外部动作",
                'items': len(result.get('items', [])), 'submitted': False}
    finally:
        store.release(token)
