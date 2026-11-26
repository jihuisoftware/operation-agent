"""Select local design only when image generation is unconfigured."""
import json
from . import visual_provider

_MAGAZINE_PREFLIGHT = '尚未配置可用的生图模型，请在模型能力设置中配置；文字草稿已保留'
_DESIGNER_PREFLIGHT = '请先配置可用的生图模型'


def no_image_model():
    from hermes_cli.config import load_config_readonly
    config = load_config_readonly().get('image_gen') or {}
    # The bundled managed route can be present even on a fresh Profile without
    # a model. An explicitly selected model/backend that is down stays an error.
    if config.get('model') or config.get('provider') not in (None, '', 'nous'):
        return False
    return not visual_provider.available()


def unstarted(db, draft):
    root = draft.get('revision_root_id') or draft['id']
    rows = db.execute("SELECT data FROM objects WHERE kind='visual_set' AND json_extract(data,'$.allowance_key')=?",
                      ('content:' + root,))
    for row in rows:
        job = json.loads(row[0])
        if (job['state'] != 'needs_attention' or job['detail'] != _MAGAZINE_PREFLIGHT
                or job.get('cancelled') or job.get('attempts') or job.get('pages') or job.get('art') or job.get('plan')):
            return False
    for row in db.execute("SELECT data FROM objects WHERE kind='designer_cover_job' AND id IN (?,?)",
                          ('designer-auto:' + root, 'designer-auto:' + draft['id'])):
        job = json.loads(row[0])
        if job['state'] != 'failed' or job.get('charged') or job.get('error') != _DESIGNER_PREFLIGHT:
            return False
    return True
