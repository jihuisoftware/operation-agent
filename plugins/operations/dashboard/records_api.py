"""Workspace overview, operational records, actions and reports."""
from fastapi import APIRouter, HTTPException
from fastapi.responses import PlainTextResponse

from .. import service
from ..store import Store
from .request_errors import checked

router = APIRouter()


@router.get("/state")
def state():
    return Store().snapshot()


@router.get("/overview")
def read_overview():
    from plugins.operations.overview import overview
    return overview(Store())


@router.get('/organized-sources')
def organized_sources(q: str = '', category: str = '', cursor: int = 0):
    from plugins.operations.organization_catalog import catalog
    if len(q) > 200 or len(category) > 30 or cursor < 0:
        raise HTTPException(400, '筛选条件无效')
    return checked(lambda: catalog(Store(), q, category, cursor))


@router.post("/records/{kind}")
def record(kind: str, body: dict):
    if kind not in {"task", "metric", "content"}:
        raise HTTPException(400, "不支持的记录类型")
    if not body or len(str(body)) > 50000:
        raise HTTPException(400, "记录内容为空或过长")
    return {"id": checked(lambda: service.add_record(Store(), kind, body))}


@router.post("/actions/{identity}/{operation}")
def manage_action(identity: str, operation: str, body: dict):
    store = Store()
    handlers = {
        "resolve": lambda: service.resolve_action(store, identity, body["state"], body["evidence"]),
        "retry": lambda: service.retry_action(store, identity),
        "cancel": lambda: service.cancel_action(store, identity),
    }
    if operation not in handlers:
        raise HTTPException(400, "不支持的操作")
    return {"result": checked(handlers[operation])}


@router.get("/reports/{day}")
def report(day: str):
    store = Store()
    reports = store.objects("report", day)
    record = next((r for r in reports if r['id']=='report:'+day),reports[0] if reports else None)
    if not record:
        raise HTTPException(404, "日报尚未生成")
    from ..daily_receipts import markdown
    with store.connection() as db:
        return PlainTextResponse(markdown(db,record,record["markdown"]), media_type="text/markdown")


@router.get('/attention/{kind}')
def attention_items(kind: str, before: int = 0, day: str = '', record: str = ''):
    from ..attention import listing
    return checked(lambda: listing(Store(), kind, before, day, record))


@router.post('/attention/inbox/handled')
def handle_inbox(body: dict):
    from ..attention import handle_inbox as handle
    from .request_errors import checked_resource
    return checked_resource(lambda: handle(Store(), body['id']))
