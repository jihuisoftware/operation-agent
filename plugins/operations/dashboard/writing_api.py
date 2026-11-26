"""Private Profile/topic-scoped writing-copy APIs."""
from fastapi import APIRouter

from .request_errors import checked_resource
from ..store import Store
from .. import writing_drafts as drafts

router = APIRouter(prefix='/content/writing-drafts')


@router.get('')
def listing(before: str = ''):
    return checked_resource(lambda: drafts.listing(Store(), before))


@router.post('')
def create(body: dict):
    return checked_resource(lambda: drafts.create(Store(), body))


@router.get('/{identity}')
def detail(identity: str):
    return checked_resource(lambda: drafts.detail(Store(), identity))


@router.put('/{identity}')
def save(identity: str, body: dict):
    return checked_resource(lambda: drafts.save(Store(), identity, body))


@router.post('/{identity}/archive')
def archive(identity: str, body: dict):
    return checked_resource(lambda: drafts.archive(Store(), identity, body))


@router.post('/{identity}/submit')
def submit(identity: str, body: dict):
    from ..writing_submission import submit as finalize
    return checked_resource(lambda: finalize(Store(), identity, body))


@router.get('/{identity}/preview')
def preview(identity: str):
    return checked_resource(lambda: drafts.detail(Store(), identity)['preview'])


@router.post('/{identity}/covers/preview')
def cover(identity: str, body: dict):
    from ..writing_covers import preview as render
    return checked_resource(lambda: render(Store(), identity, body))
