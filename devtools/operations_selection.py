"""Explicit batch selections; unselected business stages never acquire execution authority."""
from fastapi import HTTPException


def parse(body, task, mode):
    if 'tasks' not in body:
        return None
    from .operations_debug import TASKS
    tasks = body['tasks']
    if task != 'pipeline':
        raise HTTPException(400, '仅批次执行支持 tasks 列表')
    if not isinstance(tasks, list) or not tasks or any(not isinstance(value, str) or value not in TASKS for value in tasks):
        raise HTTPException(400, '请至少选择一个有效测试项目')
    if len(tasks) != len(set(tasks)):
        raise HTTPException(400, '测试项目不能重复')
    return [key for key in TASKS if key in tasks]


def require_selected(task, selected_tasks):
    if task == 'pipeline' and selected_tasks is None:
        raise HTTPException(400, '请选择本次执行项目；未携带勾选列表，任务未启动。请刷新调试页面后重试')


def bind_existing_content(store, data, policy):
    selected = data.get('selected_tasks')
    if selected is None or 'publish' not in selected or 'content' in selected:
        return
    from plugins.operations.content import validate_content
    from plugins.operations.industry import check_public_context
    from plugins.operations.organization import material_id
    sources = store.objects('source')
    by_id = {row['id']: row for row in sources}
    assets = [row for row in store.objects('asset') if row.get('authorized') and not row.get('revoked')]
    for draft in store.objects('content', data['day']):
        if not draft.get('ready') or draft.get('version') != data['version']:
            continue
        try:
            validate_content(draft, sources, assets, require_assets=True)
            check_public_context(store, draft, policy, data['day'])
            if any(row['id'] not in by_id or material_id(policy, by_id[row['id']]) != row['organization_id']
                   for row in draft.get('organized_evidence', [])):
                continue
        except ValueError:
            continue
        data['content_id'] = draft['id']
        data['reused_content_id'] = draft['id']
        store.event('selected_existing_content', {'content_id': draft['id'], 'title': draft['title'],
                                                'reason': '未勾选内容生产，绑定当前有效的已保存草稿'})
        return


def diagnostic(store, data):
    if data.get('selected_tasks') is None or 'report' in data['selected_tasks']:
        return
    from plugins.operations.report import daily_report
    previous = getattr(store, 'debug_step', None)
    store.debug_step = None
    try:
        report = daily_report(store, data['day'])
        data['diagnostic_report'] = {'id': report['id'], 'purpose': '本次实测诊断摘要，不是额外执行业务日报步骤'}
        store.event('selection_diagnostic', data['diagnostic_report'])
    finally:
        store.debug_step = previous
