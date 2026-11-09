"""Private Profile/topic-scoped writing-copy APIs."""
from fastapi import APIRouter, HTTPException

from ..store import Store
from .. import writing_drafts as drafts

router = APIRouter(prefix='/content/writing-drafts')


def checked(operation):
    try:
        return operation()
    except drafts.DraftConflict as exc:
        raise HTTPException(409, str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc
    except (ValueError, TypeError, OSError) as exc:
        raise HTTPException(400, str(exc)) from exc


@router.get('')
def listing(before: str = ''):
    return checked(lambda: drafts.listing(Store(), before))


@router.post('')
def create(body: dict):
    return checked(lambda: drafts.create(Store(), body))


@router.get('/{identity}')
def detail(identity: str):
    return checked(lambda: drafts.detail(Store(), identity))


@router.put('/{identity}')
def save(identity: str, body: dict):
    return checked(lambda: drafts.save(Store(), identity, body))


@router.post('/{identity}/archive')
def archive(identity: str, body: dict):
    return checked(lambda: drafts.archive(Store(), identity, body))


@router.post('/{identity}/submit')
def submit(identity: str, body: dict):
    from ..writing_submission import submit as finalize
    return checked(lambda: finalize(Store(), identity, body))


@router.get('/{identity}/preview')
def preview(identity: str):
    return checked(lambda: drafts.detail(Store(), identity)['preview'])


@router.post('/{identity}/covers/preview')
def cover(identity: str, body: dict):
    from ..writing_covers import preview as render
    return checked(lambda: render(Store(), identity, body))
