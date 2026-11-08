"""Private authenticated plugin API. Host middleware binds owning profile and secret scope."""
import base64
from pathlib import Path
from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import PlainTextResponse
from plugins.operations.store import Store
from plugins.operations.runtime import ensure_schedule
from plugins.operations import service
from plugins.operations.dashboard.source_api import router as source_router
from plugins.operations.dashboard.browser_api import router as browser_router

from plugins.operations.dashboard.analysis_api import router as analysis_router

from plugins.operations.dashboard.library_api import router as library_router

from plugins.operations.dashboard.workspace_api import router as workspace_router, scope_dependency

router = APIRouter(dependencies=[Depends(scope_dependency)])
router.include_router(workspace_router)
router.include_router(library_router)
router.include_router(analysis_router)
router.include_router(source_router)
router.include_router(browser_router)
from plugins.operations.dashboard.token_api import router as token_router
router.include_router(token_router)
from plugins.operations.dashboard.model_budget_api import router as model_budget_router
router.include_router(model_budget_router)
from plugins.operations.dashboard.topics_api import router as topics_router
router.include_router(topics_router)
from plugins.operations.dashboard.content_api import router as content_router
router.include_router(content_router)

# Development tooling is absent from release payloads and wheels.
_source_root = Path(__file__).resolve().parents[3]
if (_source_root / ".git").exists() and (_source_root / "devtools/operations_debug.py").is_file():
    from devtools.operations_debug import router as debug_router
    router.include_router(debug_router)


def checked(fn):
    try:
        return fn()
    except (ValueError, KeyError, TypeError) as exc:
        raise HTTPException(400, str(exc)) from exc


@router.get("/state")
def state():
    return Store().snapshot()


@router.get("/overview")
def read_overview():
    from plugins.operations.overview import overview
    return overview(Store())


@router.get('/upcoming')
def upcoming_steps():
    from plugins.operations.upcoming import upcoming
    return upcoming(Store())


@router.get("/topics")
def topics_catalog():
    from plugins.operations.topics import catalog
    return checked(lambda: catalog(Store()))


@router.get('/organized-sources')
def organized_sources(q: str = '', category: str = '', cursor: int = 0):
    from plugins.operations.organization_catalog import catalog
    if len(q) > 200 or len(category) > 30 or cursor < 0:
        raise HTTPException(400, '筛选条件无效')
    return checked(lambda: catalog(Store(), q, category, cursor))


@router.post("/topics/select")
def select_topic(body: dict):
    from plugins.operations.topics import select
    return checked(lambda: select(Store(), body))


@router.post('/upcoming/cancel')
def cancel_step(body: dict):
    from plugins.operations.upcoming import cancel
    return checked(lambda: cancel(Store(), body))


@router.get("/policy")
def read_policy():
    version, policy = Store().policy()
    from plugins.operations.readiness import web_held
    with Store().connection() as db:
        held = web_held(db)
    from plugins.operations.execution_pause import block
    return {"version": version, "policy": policy, "web_held": held, "execution_block": block(Store())}


@router.put("/policy")
def configure(body: dict):
    store = Store()
    version = checked(lambda: store.configure(body["policy"], body["version"], activation=True))
    if body["policy"].get("enabled"):
        ensure_schedule(store)
    from plugins.operations.readiness import refresh
    refresh(store)
    return {"version": version}


@router.post("/worker/poll")
def poll(body: dict):
    worker = str(body.get("worker", ""))
    if not 1 <= len(worker) <= 128:
        raise HTTPException(400, "执行者标识无效")
    store = Store()
    from plugins.operations.web_control import state as control_state, validate_intent
    intent = checked(lambda: validate_intent(body.get('takeover')))
    command = store.claim(worker, busy=body.get('busy') is True, takeover=intent, wake_only=body.get('wake_only') is True)
    with store.connection() as db:
        report = db.execute("SELECT id, json_extract(data,'$.day') AS day FROM objects WHERE kind='report' ORDER BY created DESC LIMIT 1").fetchone()
        notices = [dict(r) for r in db.execute("SELECT id,data FROM events WHERE kind='publication_notice' ORDER BY id DESC LIMIT 10")]
        control = control_state(store, db, worker)
        from plugins.operations.batch_cancellation import worker_commands
        cancellations = worker_commands(db, worker)
    import json
    from plugins.operations.execution_pause import block
    return {"command": command, 'cancel_commands': cancellations, "execution_block": block(store), 'takeover': control, "latest_report": dict(report) if report else None,
            'publication_notices': [{**json.loads(n['data']), 'id': n['id']} for n in notices]}


@router.post("/worker/ack")
def ack(body: dict):
    checked(lambda: Store().acknowledge(body["id"], body["worker"], body["result"]))
    return {"ok": True}


@router.get("/assets/{identity}")
def asset(identity: str, thumbnail: bool = False):
    from plugins.plugin_storage import plugin_data_dir
    store = Store()
    row = next((a for a in store.objects("asset") if a["id"] == identity and not a.get("revoked")), None)
    if not row:
        raise HTTPException(404, "素材不存在或已撤回")
    data = (plugin_data_dir("operations") / "assets" / row["file"]).read_bytes()
    if thumbnail:
        from plugins.operations.asset_views import thumbnail_data
        return checked(lambda: thumbnail_data(row['name'], data))
    return {"name": row["name"], "data": base64.b64encode(data).decode()}


@router.post("/assets")
def add_asset(body: dict):
    identity = checked(lambda: Store().add_asset(body["name"], base64.b64decode(body["data"], validate=True), body.get("authorized") is True))
    from plugins.operations.readiness import refresh
    refresh(Store())
    return {"id": identity}


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


@router.post("/assets/{identity}/revoke")
def revoke(identity: str):
    checked(lambda: service.revoke_asset(Store(), identity))
    return {"ok": True}


@router.get("/reports/{day}")
def report(day: str):
    record = next((r for r in Store().objects("report") if r["day"] == day), None)
    if not record:
        raise HTTPException(404, "日报尚未生成")
    return PlainTextResponse(record["markdown"], media_type="text/markdown")


@router.get("/content/{identity}/export")
def export_content(identity: str):
    from io import BytesIO
    import json
    from zipfile import ZipFile
    from plugins.plugin_storage import plugin_data_dir
    store = Store()
    content = next((c for c in store.objects("content") if c["id"] == identity), None)
    if not content:
        raise HTTPException(404, "内容版本不存在")
    assets = {a["id"]: a for a in store.objects("asset") if not a.get("revoked")}
    if not set(content["asset_ids"]) <= set(assets):
        raise HTTPException(400, "内容引用的素材已撤回授权")
    buffer = BytesIO()
    with ZipFile(buffer, "w") as archive:
        archive.writestr("content.json", json.dumps(content, ensure_ascii=False, indent=2))
        archive.writestr("正文.md", f"# {content['title']}\n\n{content['body']}\n")
        sources = [s for s in store.objects("source") if s["id"] in content["source_ids"]]
        archive.writestr("sources.json", json.dumps(sources, ensure_ascii=False, indent=2))
        for index, asset_id in enumerate(content["asset_ids"]):
            row = assets[asset_id]
            archive.write(plugin_data_dir("operations") / "assets" / row["file"], f"images/{index + 1}-{row['file']}")
    return {"data": base64.b64encode(buffer.getvalue()).decode()}


@router.get("/blueprints")
def blueprints_catalog():
    from plugins.operations.blueprints import catalog
    return catalog(Store())


@router.post("/blueprints/preview")
def blueprints_preview(body: dict):
    from plugins.operations.blueprints import preview
    return checked(lambda: preview(Store(), body))


@router.post("/blueprints/apply")
def blueprints_apply(body: dict):
    from plugins.operations.blueprints import apply
    return checked(lambda: apply(Store(), body))


@router.get("/platforms")
def platforms(worker: str | None = None):
    from plugins.operations.login_status import catalog
    return catalog(Store(), worker)


@router.post("/platforms/observe")
def platform_observation(body: dict):
    from plugins.operations.login_status import observe
    store = Store()
    result = checked(lambda: observe(store, body))
    from plugins.operations.readiness import refresh
    refresh(store)
    return result


@router.post('/quick-start')
def quick_start(body: dict):
    from plugins.operations.quick_start import apply
    return checked(lambda: apply(Store(), body))


@router.get('/quick-start')
def first_run_status():
    from plugins.operations.quick_start import status
    return status(Store())


@router.post('/worker/takeover')
def web_takeover(body: dict):
    from plugins.operations.readiness import takeover
    return checked(lambda: takeover(Store(), body.get('worker'), body.get('active')))


@router.post('/plan/control')
def plan_control(body: dict):
    from plugins.operations.plan_controls import control
    return checked(lambda: control(Store(), body))


@router.post('/quick-start/cancel')
def cancel_first_run(body: dict):
    from plugins.operations.plan_controls import cancel_first
    return checked(lambda: cancel_first(Store(), body['id']))


from plugins.operations.dashboard.resume_api import router as resume_router
router.include_router(resume_router)
