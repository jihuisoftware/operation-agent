"""Private human review and per-manuscript publication scheduling."""
from fastapi import APIRouter, HTTPException

from ..store import Store
from .. import content_release

router = APIRouter(prefix='/content')


@router.post('/generate')
def generate(body: dict):
    from ..content_runs import generate as create
    try:
        return create(Store(), body)
    except (ValueError, KeyError, TypeError) as exc:
        raise HTTPException(400, str(exc)) from exc


@router.post('/{identity}/approve')
def approve(identity: str, body: dict):
    try:
        store = Store()
        from ..runtime import ensure_schedule
        ensure_schedule(store)
        return content_release.review(store, identity, body)
    except (ValueError, KeyError, TypeError, OSError) as exc:
        raise HTTPException(400, str(exc)) from exc


@router.post('/{identity}/cancel-schedule')
def cancel(identity: str, body: dict):
    try:
        return content_release.cancel(Store(), identity, body['expected_revision'])
    except (ValueError, KeyError, TypeError) as exc:
        raise HTTPException(400, str(exc)) from exc
