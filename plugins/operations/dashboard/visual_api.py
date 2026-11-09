"""Visual production uses private Profile/topic-scoped endpoints, never publication authority."""
from fastapi import APIRouter

from .writing_api import checked
from ..store import Store
from .. import visual_jobs, visual_job_state

router = APIRouter(prefix='/visual-sets')


@router.get('')
def latest(kind: str, identity: str):
    return checked(lambda: visual_jobs.latest(Store(), kind, identity))


@router.post('')
def start(body: dict):
    return checked(lambda: visual_jobs.start(Store(), body))


@router.get('/{identity}')
def detail(identity: str):
    return checked(lambda: visual_jobs.public(visual_job_state.status(Store(), identity)))


@router.post('/{identity}/cancel')
def cancel(identity: str):
    return checked(lambda: visual_jobs.cancel(Store(), identity))


@router.post('/{identity}/apply')
def apply(identity: str, body: dict):
    return checked(lambda: visual_jobs.apply(Store(), identity, body))


@router.post('/{identity}/restore')
def restore(identity: str):
    return checked(lambda: visual_jobs.restore(Store(), identity))
