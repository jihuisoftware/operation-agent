"""Private, topic-bound received-message workbench."""

from fastapi import APIRouter, HTTPException

from .. import messages
from ..message_actions import change
from ..store import Store
from .request_errors import checked_resource

router = APIRouter(prefix="/messages")


@router.get("")
def listing(source: str = "", state: str = "", before: int = 0):
    return checked_resource(lambda: messages.listing(Store(), source, state, before))


@router.get("/{identity:path}")
def detail(identity: str):
    return checked_resource(lambda: messages.detail(Store(), identity))


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
