"""Private authenticated plugin API. Host middleware binds owning profile and secret scope."""
import base64
from fastapi import APIRouter, HTTPException
from fastapi.responses import PlainTextResponse
from plugins.operations.store import Store
from plugins.operations.runtime import ensure_schedule
from plugins.operations import service

router = APIRouter()


def checked(fn):
    try:
        return fn()
    except (ValueError, KeyError, TypeError) as exc:
        raise HTTPException(400, str(exc)) from exc


@router.get("/state")
def state():
    return Store().snapshot()


@router.get('/upcoming')
def upcoming_steps():
    from plugins.operations.upcoming import upcoming
    return upcoming(Store())


@router.post('/upcoming/cancel')
def cancel_step(body: dict):
    from plugins.operations.upcoming import cancel
    return checked(lambda: cancel(Store(), body))


@router.get("/policy")
def read_policy():
    version, policy = Store().policy()
    return {"version": version, "policy": policy}


@router.put("/policy")
def configure(body: dict):
    store = Store()
    version = checked(lambda: store.configure(body["policy"], body["version"]))
    if body["policy"].get("enabled"):
        ensure_schedule(store)
    return {"version": version}


@router.post("/worker/poll")
def poll(body: dict):
    worker = str(body.get("worker", ""))
    if not 1 <= len(worker) <= 128:
        raise HTTPException(400, "执行者标识无效")
    store = Store()
    with store.connection() as db:
        report = db.execute("SELECT id, json_extract(data,'$.day') AS day FROM objects WHERE kind='report' ORDER BY created DESC LIMIT 1").fetchone()
    return {"command": store.claim(worker, busy=body.get("busy") is True), "latest_report": dict(report) if report else None}


@router.post("/worker/ack")
def ack(body: dict):
    checked(lambda: Store().acknowledge(body["id"], body["worker"], body["result"]))
    return {"ok": True}


@router.get("/assets/{identity}")
def asset(identity: str):
    from plugins.plugin_storage import plugin_data_dir
    store = Store()
    row = next((a for a in store.objects("asset") if a["id"] == identity and not a.get("revoked")), None)
    if not row:
        raise HTTPException(404, "素材不存在或已撤回")
    data = (plugin_data_dir("operations") / "assets" / row["file"]).read_bytes()
    return {"name": row["name"], "data": base64.b64encode(data).decode()}


@router.post("/assets")
def add_asset(body: dict):
    identity = checked(lambda: Store().add_asset(body["name"], base64.b64decode(body["data"], validate=True), body.get("authorized") is True))
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
    return checked(lambda: observe(Store(), body))
