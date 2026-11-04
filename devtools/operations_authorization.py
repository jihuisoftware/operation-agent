"""Persist only the action scope explicitly requested by a quick live test."""
from fastapi import HTTPException

from plugins.operations.debug_authorization import grant_id
from plugins.operations.modules import ACTION_MODULE
from plugins.operations.policy import now_iso


def request_mode(body, task, mode):
    value = body.get('external_actions')
    if value not in (None, 'execute_once') or (value and mode != 'quick'):
        raise HTTPException(400, '外部动作调试方式无效')
    external = task in ACTION_MODULE or task == 'pipeline'
    if mode == 'quick' and external and value != 'execute_once':
        raise HTTPException(400, '快速实测会执行真实外部动作，请刷新调试页后点击真实执行按钮')
    return 'execute_once' if mode == 'quick' and external else 'standing_policy'


def create(store, data):
    if data.get('action_mode') != 'execute_once':
        return
    actions = sorted(ACTION_MODULE) if data['task'] == 'pipeline' else [data['task']]
    scope = ({'business_id': store.scope['business_id'], 'topic_id': store.scope['id'], 'account': store.scope['account']}
             if store.scope else None)
    grant = {'batch': data['id'], 'version': data['version'], 'day': data['day'], 'actions': actions,
             'max_per_kind': 1, 'created': now_iso(), 'scope': scope, 'database': str(store.path.resolve())}
    store.put('debug_action_grant', grant, grant_id(data['id']))
    store.event('debug_authorization', grant)
