"""Private topic-scoped review configuration and explicit single-manuscript rechecks."""
from fastapi import APIRouter, HTTPException
from ..store import Store
from .. import review_policy, automatic_review

router = APIRouter()


@router.get('/review-policy')
def policy():
    return review_policy.get(Store())


@router.put('/review-policy')
def update(body: dict):
    try:
        return review_policy.update(Store(), body)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc


@router.post('/content/{identity}/recheck-review')
def recheck(identity: str, body: dict):
    try:
        return automatic_review.recheck(Store(), identity, body)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc


@router.post('/content/{identity}/manual-review')
def manual(identity: str, body: dict):
    try:
        return automatic_review.require_manual(Store(), identity, body)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
