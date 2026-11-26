"""Desktop worker commands, takeover and platform observations."""
import json

from fastapi import APIRouter, HTTPException

from ..store import Store
from .request_errors import checked

router = APIRouter()


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
    from plugins.operations.execution_pause import block
    return {"command": command, 'cancel_commands': cancellations, "execution_block": block(store), 'takeover': control, "latest_report": dict(report) if report else None,
            'publication_notices': [{**json.loads(n['data']), 'id': n['id']} for n in notices]}


@router.post("/worker/ack")
def ack(body: dict):
    checked(lambda: Store().acknowledge(body["id"], body["worker"], body["result"]))
    return {"ok": True}


@router.post('/worker/takeover')
def web_takeover(body: dict):
    from plugins.operations.readiness import takeover
    return checked(lambda: takeover(Store(), body.get('worker'), body.get('active')))


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
