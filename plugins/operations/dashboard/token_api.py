"""Authenticated Profile-wide analytics; scope filters are separately validated."""
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from ..token_usage import UsageQuery

router = APIRouter()


def query(request):
    params = request.query_params
    selected = {key: params.get('filter_' + key, '') for key in ('business', 'topic', 'module', 'model', 'provider', 'purpose')}
    try:
        return UsageQuery(period=params.get('period', 'day'), tz=params.get('tz', 'Asia/Shanghai'),
                          until=params.get('until'), selected=selected)
    except (ValueError, OverflowError) as exc:
        raise HTTPException(400, str(exc)) from exc


@router.get('/usage/summary')
def summary(request: Request):
    return query(request).summary()


@router.get('/usage/tasks')
def tasks(request: Request):
    try:
        return query(request).tasks(request.query_params.get('cursor'))
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.get('/usage/tasks/{identity}/calls')
def calls(identity: str, request: Request):
    try:
        return query(request).calls(identity, request.query_params.get('cursor'))
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.get('/usage/export')
def export(request: Request):
    # Capture Profile path before StreamingResponse moves iteration to a worker thread.
    from hermes_constants import get_hermes_home
    selected = query(request)
    selected.path = get_hermes_home() / 'state.db'
    if request.query_params.get('transport') == 'json':
        return {'csv': ''.join(selected.export())}
    return StreamingResponse(selected.export(), media_type='text/csv', headers={'Content-Disposition': 'attachment; filename="token-usage.csv"'})
