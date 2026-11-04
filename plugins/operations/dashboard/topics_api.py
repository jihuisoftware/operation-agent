"""Explicit topic regeneration stays behind the shared authenticated workspace scope."""
from fastapi import APIRouter, HTTPException

from ..store import Store
from ..topic_runs import run

router = APIRouter(prefix='/topics')


@router.post('/generate')
def generate(body: dict):
    try:
        return run(Store(), body)
    except (ValueError, KeyError, TypeError) as exc:
        raise HTTPException(400, str(exc)) from exc
