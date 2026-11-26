"""Authorized assets and downloadable manuscript bundles."""
import base64

from fastapi import APIRouter, HTTPException

from .. import service
from ..store import Store
from .request_errors import checked

router = APIRouter()


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
    store = Store()
    identity = checked(lambda: store.add_asset(body["name"], base64.b64decode(body["data"], validate=True), body.get("authorized") is True))
    from plugins.operations.readiness import refresh
    refresh(store)
    return {"id": identity}


@router.post("/assets/{identity}/revoke")
def revoke(identity: str):
    checked(lambda: service.revoke_asset(Store(), identity))
    return {"ok": True}


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
