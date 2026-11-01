"""Profile-owned material library, with local image previews rather than remote hotlinks."""
import base64
import json

from fastapi import APIRouter, HTTPException, Query

from plugins.operations.store import Store
from plugins.operations import source_library

router = APIRouter(prefix="/sources")


@router.get("")
def catalog(q: str = Query(default="", max_length=200), cursor: int = Query(default=0, ge=0)):
    return source_library.catalog(Store(), q, cursor)


@router.get("/images/{identity}")
def image(identity: str):
    from plugins.operations.source_media import directory
    store = Store()
    with store.connection() as db:
        row = db.execute("SELECT data FROM objects WHERE kind='source_image' AND id=?", (identity,)).fetchone()
    if not row:
        raise HTTPException(404, "参考图片不存在")
    data = json.loads(row[0])
    path = directory(store) / data["file"]
    if not path.is_file():
        raise HTTPException(404, "参考图片文件已不可用")
    return {"mime": data["mime"], "data": base64.b64encode(path.read_bytes()).decode(), "authorized": False}


@router.get("/{identity}")
def detail(identity: str):
    try:
        return source_library.detail(Store(), identity)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.post("/{identity}/reuse")
def reuse(identity: str, body: dict):
    try:
        return source_library.reuse(Store(), identity, body)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
