"""Translate invalid operations request data to an HTTP client error."""
from fastapi import HTTPException


def checked(fn):
    try:
        return fn()
    except (ValueError, KeyError, TypeError) as exc:
        raise HTTPException(400, str(exc)) from exc


def checked_resource(operation):
    from ..writing_drafts import DraftConflict
    try:
        return operation()
    except DraftConflict as exc:
        raise HTTPException(409, str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc
    except (ValueError, TypeError, OSError) as exc:
        raise HTTPException(400, str(exc)) from exc
