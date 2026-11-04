"""Profile-wide budget settings behind the existing private plugin scope."""
from fastapi import APIRouter, HTTPException

from ..model_budget_settings import read, save
from ..store import Store

router = APIRouter()


@router.get('/model-budget')
def read_budget():
    return read(Store())


@router.put('/model-budget')
def save_budget(body: dict):
    try:
        return save(Store(), body)
    except (ValueError, KeyError, TypeError) as exc:
        raise HTTPException(400, str(exc)) from exc
