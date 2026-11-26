"""Operations plans, scheduling and first-run controls."""
from fastapi import APIRouter

from ..runtime import ensure_schedule
from ..store import Store
from .request_errors import checked

router = APIRouter()


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
    store = Store()
    version, policy = store.policy()
    from plugins.operations.readiness import web_held
    with store.connection() as db:
        held = web_held(db)
    from plugins.operations.execution_pause import block
    return {"version": version, "policy": policy, "web_held": held, "execution_block": block(store)}


@router.put("/policy")
def configure(body: dict):
    store = Store()
    version = checked(lambda: store.configure(body["policy"], body["version"], activation=True))
    if body["policy"].get("enabled"):
        ensure_schedule(store)
    from plugins.operations.readiness import refresh
    refresh(store)
    return {"version": version}


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


@router.post('/quick-start')
def quick_start(body: dict):
    from plugins.operations.quick_start import apply
    return checked(lambda: apply(Store(), body))


@router.get('/quick-start')
def first_run_status():
    from plugins.operations.quick_start import status
    return status(Store())


@router.post('/quick-start/cancel')
def cancel_first_run(body: dict):
    from plugins.operations.plan_controls import cancel_first
    return checked(lambda: cancel_first(Store(), body['id']))


@router.post('/plan/control')
def plan_control(body: dict):
    from plugins.operations.plan_controls import control
    return checked(lambda: control(Store(), body))
