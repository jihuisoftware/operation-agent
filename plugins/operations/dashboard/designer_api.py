"""Topic-scoped orchestration for the external cover-designer package."""
from fastapi import APIRouter
from .writing_api import checked
from .. import designer_jobs, designer_apply
from ..store import Store

router = APIRouter(prefix='/cover-designer')


@router.get('')
def latest(kind: str, origin_id: str):
    return checked(lambda: designer_jobs.latest(Store(), kind, origin_id))


@router.post('')
def start(body: dict):
    return checked(lambda: designer_jobs.start(Store(), body))


@router.get('/{job}')
def detail(job: str):
    return checked(lambda: designer_jobs.status(Store(), job))


@router.post('/{job}/apply')
def apply(job: str, body: dict):
    return checked(lambda: designer_apply.apply(Store(), job, body))
