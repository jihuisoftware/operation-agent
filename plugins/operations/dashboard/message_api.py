"""Shared account inbox, with operations scoped to the handling topic."""

from fastapi import APIRouter, HTTPException

from .. import messages
from ..message_actions import change
from ..store import Store
from .request_errors import checked_resource

router = APIRouter(prefix="/messages")


@router.get("")
def listing(source: str = "", state: str = "", before: str = "0", platform: str = ""):
    return checked_resource(lambda: messages.listing(Store(), source, state, before, account_view=True, platform=platform))


@router.get("/{identity:path}")
def detail(identity: str):
    return checked_resource(lambda: messages.detail(Store(), identity, account_view=True))


@router.post("/sync-notifications")
def sync_notifications(body: dict | None = None):
    from ..notification_intake import sync
    from ..execution_pause import ExecutionPaused
    from ..outcomes import StageSkipped
    try:
        return checked_resource(lambda: sync(Store(), platform=(body or {}).get("platform", "xiaohongshu")))
    except (ExecutionPaused, StageSkipped) as exc:
        raise HTTPException(409, str(exc)) from exc


@router.post("/{identity}")
def update(identity: str, body: dict):
    try:
        return change(Store(), identity, body)
    except messages.Conflict as exc:
        raise HTTPException(409, str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
