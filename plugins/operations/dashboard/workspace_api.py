"""Private workspace endpoints; Profile binding is supplied by the host."""
import json
from fastapi import APIRouter, HTTPException, Request

from ..workspaces import ACTIVE_SCOPE, Workspaces

router = APIRouter()


async def scope_dependency(request: Request):
    if '/usage/' in request.url.path:
        yield
        return
    business = request.query_params.get('business_id')
    topic = request.query_params.get('topic_id')
    try:
        directory = Workspaces()
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    if not business and not topic and request.url.path.endswith(('/workspaces', '/workspaces/summary', '/workspaces/worker/poll', '/workspaces/selection')):
        yield
        return
    try:
        scope = directory.resolve(business, topic)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc
    if (scope['archived'] or scope['business_archived']) and request.method not in {'GET', 'HEAD'} and not request.url.path.endswith(('/workspaces', '/workspaces/worker/poll', '/workspaces/selection', '/resolve')):
        raise HTTPException(409, '已归档内容为只读')
    token = ACTIVE_SCOPE.set((scope['business_id'], scope['id']))
    try:
        yield
    finally:
        ACTIVE_SCOPE.reset(token)


@router.get('/workspaces')
def catalog():
    return Workspaces().catalog()


@router.put('/workspaces/selection')
def selection(body: dict):
    directory = Workspaces()
    try:
        scope = directory.resolve(body['business_id'], body['topic_id'])
    except (ValueError, KeyError) as exc:
        raise HTTPException(404, str(exc)) from exc
    with directory.connection() as db:
        db.execute("INSERT OR REPLACE INTO preferences VALUES ('selection',?)", (json.dumps({'business_id': scope['business_id'], 'topic_id': scope['id']}),))
    return {'ok': True}


@router.post('/workspaces')
def manage(body: dict):
    directory = Workspaces()
    try:
        action = body.get('action')
        if action == 'create':
            return directory.create(body.get('name', ''), business=body.get('business_id'), category=body.get('category', ''), copy_topic=body.get('copy_topic'))
        if action == 'rename':
            directory.rename(body['kind'], body['id'], body['name'])
        elif action in {'archive', 'pause', 'resume'}:
            directory.update_state(body['kind'], body.get('id'), action)
        elif action == 'link_account':
            from ..workspace_execution import link_account
            link_account(directory, body['business_id'], body['account_id'])
        else:
            raise ValueError('未知业务管理操作')
        return directory.catalog()
    except (ValueError, KeyError) as exc:
        raise HTTPException(400, str(exc)) from exc


@router.get('/workspaces/summary')
def summary():
    directory = Workspaces()
    items = []
    for topic in directory.catalog()['topics']:
        store = directory.store(topic['business_id'], topic['id'])
        version, policy = store.policy()
        with store.connection() as db:
            counts = {r[0]: r[1] for r in db.execute('SELECT kind,count(*) FROM objects GROUP BY kind')}
            running = [dict(r) for r in db.execute("SELECT * FROM runs WHERE state='running'")]
            latest = db.execute('SELECT * FROM runs ORDER BY started DESC LIMIT 1').fetchone()
            debug_running = db.execute("SELECT count(*) FROM objects WHERE kind='debug_run' AND json_extract(data,'$.state')='running'").fetchone()[0]
        items.append({**topic, 'version': version, 'enabled': policy['enabled'], 'paused': policy['paused'] or directory.blocked(store.scope), 'counts': counts, 'running': running, 'debug_running': debug_running, 'latest': dict(latest) if latest else None})
    return {'items': items}


@router.post('/workspaces/worker/poll')
def poll_account(body: dict):
    directory = Workspaces()
    account, worker = body.get('account_id'), body.get('worker')
    if not isinstance(worker, str) or not 1 <= len(worker) <= 128:
        raise HTTPException(400, '执行器标识无效')
    catalog = directory.catalog()
    if account not in {a['id'] for a in catalog['accounts']}:
        raise HTTPException(404, '账号不存在')
    from ..workspace_broker import poll
    return poll(directory, account, worker, body.get('busy') is True)


@router.get('/workspaces/references/{topic_id}')
def reference_catalog(topic_id: str):
    from ..store import Store
    current = Store()
    try:
        original = current.workspace.store(current.scope['business_id'], topic_id)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc
    return {'items': [{'id': r['id'], 'title': r.get('title', ''), 'summary': r.get('summary', ''), 'url': r.get('url', '')} for r in original.objects('source') if r.get('text')][:100]}


@router.post('/workspaces/reference')
def reference(body: dict):
    from ..store import Store
    from ..workspace_topics import reference_source
    try:
        return reference_source(Store(), body['source_topic_id'], body['source_id'])
    except (ValueError, KeyError) as exc:
        raise HTTPException(400, str(exc)) from exc


@router.post('/workspaces/transfer-inbox')
def transfer_inbox(body: dict):
    from ..store import Store
    from ..workspace_inbox import transfer
    try:
        return transfer(Store(), body)
    except (ValueError, KeyError) as exc:
        raise HTTPException(400, str(exc)) from exc
