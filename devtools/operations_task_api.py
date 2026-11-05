"""Source-only task drill-down endpoints; parent router supplies profile/workspace auth."""
from fastapi import APIRouter
from plugins.operations.store import Store
from . import operations_task_details as details

router = APIRouter()


@router.get('/tasks/{task}/runs')
def history(task: str, before: int = 0):
    return details.history(Store(), task, before)


@router.get('/{batch}/tasks/{task}')
def view(batch: str, task: str, after: int = 0):
    return details.view(Store(), batch, task, after)


@router.get('/{batch}/tasks/{task}/artifacts/{identity}')
def artifact(batch: str, task: str, identity: str):
    return details.artifact(Store(), batch, task, identity)


@router.get('/{batch}/tasks/{task}/export')
def export(batch: str, task: str):
    return details.view(Store(), batch, task, full=True)


@router.post('/{batch}/tasks/{task}/notes')
def note(batch: str, task: str, body: dict):
    return details.note(Store(), batch, task, body)
