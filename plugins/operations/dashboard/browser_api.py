"""Private browser evidence endpoints; the host binds the owning Profile."""
import json
from fastapi import APIRouter, HTTPException
from plugins.operations.store import Store
from plugins.operations import browser_evidence
from plugins.operations.publication_images import verify_images

router = APIRouter()


@router.post('/worker/interrupted')
def interrupted(body: dict):
    from ..sleep_receipts import accept
    return checked(lambda: accept(Store(), body))


def checked(fn):
    from ..batch_cancellation import BatchCancelled
    try:
        return fn()
    except BatchCancelled as exc:
        raise HTTPException(409, str(exc)) from exc
    except (ValueError, KeyError, TypeError, OSError) as exc:
        raise HTTPException(400, str(exc)) from exc


@router.post('/worker/steps')
def record_step(body: dict):
    return checked(lambda: browser_evidence.record_step(Store(), body['command_id'], body['worker'],
                   {k: v for k, v in body.items() if k not in {'command_id', 'worker'}}))


@router.post('/worker/verify-images')
def images(body: dict):
    return checked(lambda: verify_images(Store(), body['command_id'], body['worker'], body['urls']))


@router.get('/actions/{identity}/steps')
def steps(identity: str):
    return {'steps': checked(lambda: browser_evidence.steps(Store(), identity))}


@router.get('/browser-evidence/{identity}')
def evidence(identity: str):
    with Store().connection() as db:
        row = db.execute("SELECT data FROM objects WHERE id=? AND kind='browser_evidence'", (identity,)).fetchone()
    if not row:
        raise HTTPException(404, '截图不存在')
    return json.loads(row[0])


@router.get('/actions/{identity}/detail')
def action_detail(identity: str):
    from plugins.operations.action_details import detail
    return checked(lambda: detail(Store(), identity))


@router.post('/actions/{identity}/check')
def check_action(identity: str):
    from plugins.operations.review_queue import request_check
    return checked(lambda: request_check(Store(), identity))


@router.get('/actions/{identity}/snapshot/images/{asset_id}')
def snapshot_image(identity: str, asset_id: str):
    from plugins.operations.publication_snapshot import image
    return checked(lambda: image(Store(), identity, asset_id))


@router.get('/actions/{identity}/diagnostic')
def export_diagnostic(identity: str):
    from plugins.operations.evidence_storage import diagnostic
    return checked(lambda: diagnostic(Store(), identity))


@router.get('/evidence-storage')
def storage_status():
    from plugins.operations.evidence_storage import statistics
    return statistics(Store())


@router.put('/evidence-storage')
def storage_settings(body: dict):
    from plugins.operations.evidence_storage import configure
    return checked(lambda: configure(Store(), body))


@router.post('/evidence-storage/cleanup')
def cleanup_evidence():
    from plugins.operations.evidence_storage import cleanup
    return checked(lambda: cleanup(Store()))
