"""Authenticated plugin endpoints; profile scope is bound by the existing host."""
from fastapi import APIRouter, HTTPException

from ..store import Store
from .. import analysis_config, analysis_runs, analysis_views, business_store

router = APIRouter(prefix='/analysis')


def checked(fn):
    try:
        return fn()
    except (ValueError, KeyError, TypeError) as exc:
        raise HTTPException(400, str(exc)) from exc


@router.get('')
def catalog():
    return analysis_views.catalog(Store())


@router.post('/settings')
def configure(body: dict):
    return checked(lambda: analysis_config.configure(Store(), body))


@router.post('/upload')
def upload(body: dict):
    return checked(lambda: business_store.upload(Store(), body))


@router.post('/sheet')
def sheet(body: dict):
    return checked(lambda: business_store.inspect(Store(), body['upload_id'], body['sheet']))


@router.post('/preview')
def preview(body: dict):
    return checked(lambda: business_store.preview(Store(), body))


@router.post('/confirm')
def confirm(body: dict):
    return checked(lambda: business_store.confirm(Store(), body))


@router.post('/datasets/{identity}/preview')
def permissions_preview(identity: str, body: dict):
    return checked(lambda: business_store.permission_preview(Store(), identity, body))


@router.post('/datasets/{identity}')
def permissions(identity: str, body: dict):
    return checked(lambda: business_store.update_dataset(Store(), identity, body))


@router.post('/run/{stage}')
def run(stage: str, body: dict):
    return checked(lambda: analysis_runs.run(Store(), stage, body))


@router.post('/cancel/{identity}')
def cancel(identity: str):
    return checked(lambda: analysis_runs.cancel(Store(), identity))


@router.get('/logs/{identity}')
def logs(identity: str):
    return checked(lambda: analysis_runs.logs(Store(), identity))


@router.get('/reports/{identity}')
def report(identity: str):
    return checked(lambda: analysis_views.detail(Store(), identity))


@router.get('/reports/{identity}/export')
def export(identity: str, format: str = 'markdown', public: bool = False):
    return checked(lambda: analysis_views.export(Store(), identity, format, public))
