"""Private human review and per-manuscript publication scheduling."""
from fastapi import APIRouter, HTTPException

from ..store import Store
from .. import content_release

router = APIRouter(prefix='/content')


@router.get('/cover-options')
def cover_options():
    from ..cover_design import options
    return options()


@router.post('/{identity}/covers/preview')
def cover_preview(identity: str, body: dict):
    from ..cover_studio import preview
    try:
        return preview(Store(), identity, body)
    except (ValueError, KeyError, TypeError, OSError) as exc:
        raise HTTPException(400, str(exc)) from exc


@router.get('/editor-options')
def options():
    from ..content_library import editor_options
    with Store().connection() as db:
        return editor_options(db, {})


@router.post('/{identity}/versions')
def save_version(identity: str, body: dict):
    from ..content_versions import create
    try:
        return create(Store(), identity, body)
    except (ValueError, KeyError, TypeError, OSError) as exc:
        raise HTTPException(400, str(exc)) from exc


@router.get('/{identity}/details')
def details(identity: str):
    from ..content_library import detail
    try:
        return detail(Store(), identity)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.get('/publications/{identity}')
def publication(identity: str):
    from ..content_library import detail
    try:
        return detail(Store(), identity, publication=True)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc


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
