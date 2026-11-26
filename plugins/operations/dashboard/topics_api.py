"""Explicit topic regeneration stays behind the shared authenticated workspace scope."""
from fastapi import APIRouter

from .request_errors import checked
from ..store import Store
from ..topic_runs import run

router = APIRouter(prefix='/topics')


@router.post('/generate')
def generate(body: dict):
    return checked(lambda: run(Store(), body))


@router.get("")
def topics_catalog():
    from plugins.operations.topics import catalog
    return checked(lambda: catalog(Store()))


@router.post("/select")
def select_topic(body: dict):
    from plugins.operations.topics import select
    return checked(lambda: select(Store(), body))
