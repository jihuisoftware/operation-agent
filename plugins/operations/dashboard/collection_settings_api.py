"""Private, scope-bound source allowance settings; saving never starts a batch."""
from fastapi import APIRouter

from .request_errors import checked_resource
from ..store import Store
from .. import collection_settings

router = APIRouter(prefix='/collection-budget')


@router.get('')
def read():
    return checked_resource(lambda: collection_settings.read(Store()))


@router.put('')
def save(body: dict):
    return checked_resource(lambda: collection_settings.save(Store(), body))
