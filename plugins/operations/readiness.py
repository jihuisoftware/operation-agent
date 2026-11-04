"""Setup readiness is independent of authorization and execution receipts."""
import json
from datetime import datetime, UTC

from .modules import TIMES, EXTERNAL
from .policy import now_iso


def web_held(db):
    return bool(web_block_reason(db))


def web_block_reason(db):
    from .web_control import block_reason
    return block_reason(db)


def takeover(store, worker, active):
    from .store import encoded
    if not isinstance(worker, str) or not 1 <= len(worker) <= 128 or type(active) is not bool:
        raise ValueError('执行器或接管状态无效')
    with store.connection() as db:
        db.execute('BEGIN IMMEDIATE')
        if store.workspace:
            from .workspace_broker import takeover as account_takeover
            account_takeover(store, db, worker, active)
            db.execute("DELETE FROM objects WHERE kind='web_hold'")
        else:
            from .web_control import legacy_holds
            if any(data['worker'] != worker for _, data in legacy_holds(db)):
                raise ValueError('另一执行窗口正在人工接管，请在该窗口结束接管')
            db.execute("DELETE FROM objects WHERE kind='web_hold'")
            if active:
                import time
                db.execute("INSERT OR REPLACE INTO objects VALUES (?, 'web_hold', ?, ?)",
                           ('web-hold:' + worker, encoded({'worker': worker, 'active': True, 'seen': time.time()}), now_iso()))
        if active:
            db.execute("UPDATE commands SET state='cancelled' WHERE state='queued'")
            db.execute("UPDATE actions SET state='cancelled' WHERE state='queued'")
    refresh(store)
    return {'held': active}


def conditions(store, policy):
    from .blueprints import requirements
    from .login_status import catalog
    assets = store.objects('asset')
    login = next(p for p in catalog(store)['platforms'] if p['id'] == 'xiaohongshu')
    with store.connection() as db:
        held = web_block_reason(db)
        present = {r[0] for r in db.execute("SELECT DISTINCT kind FROM objects WHERE json_extract(data,'$.scope_topic')=?", (policy['topic'],))}
    upstream = {'organize': 'source', 'topics': 'organized_source', 'content': 'organized_source', 'publish': 'content', 'industry': 'analytics_report'}
    rows = {}
    for stage in TIMES:
        reasons = requirements(policy, stage, assets)
        if stage in EXTERNAL:
            if held:
                reasons.append(held)
            if login['state'] != 'logged_in' or (bool(policy['account_id']) and login['account_id'] != policy['account_id']) or login['observed_state'] == 'verification':
                reasons.append('登录并确认小红书账号')
        waiting = stage in upstream and upstream[stage] not in present
        rows[stage] = {'waiting_upstream': waiting, 'selected': policy['modules'][stage], 'ready': not reasons, 'reasons': reasons,
                       'action': setup_action(stage, reasons)}
    return rows


def refresh(store, now=None):
    """Only user-supplied setup changes establish a future scheduling boundary."""
    from .store import encoded
    _, policy = store.policy()
    rows = conditions(store, policy)
    stamp = (now or datetime.now(UTC)).astimezone(UTC).isoformat()
    with store.connection() as db:
        db.execute('BEGIN IMMEDIATE')
        for stage, value in rows.items():
            key = 'readiness:' + stage
            old = db.execute('SELECT data FROM objects WHERE id=?', (key,)).fetchone()
            prior = json.loads(old[0]) if old else {}
            boundary = prior.get('after')
            if prior.get('ready') is False and value['ready']:
                boundary = stamp
            value['after'] = boundary
            db.execute("INSERT OR REPLACE INTO objects VALUES (?, 'readiness', ?, ?)", (key, encoded(value), stamp))
    return rows


def boundaries(store):
    with store.connection() as db:
        rows = list(db.execute("SELECT id,data FROM objects WHERE kind IN ('readiness','activation')"))
    values = {r['id']: json.loads(r['data']) for r in rows}
    activation = values.get('plan-activation', {}).get('after')
    return {stage: max(filter(None, [activation, values.get('readiness:' + stage, {}).get('after')]), default='', key=datetime.fromisoformat) for stage in TIMES}


def model_setup():
    """Credential presence only; never probe a model or a cloud metadata service."""
    from hermes_cli.config import load_config_readonly
    from hermes_cli.auth import get_active_provider, get_api_key_provider_status
    from providers import get_provider_profile
    config = load_config_readonly().get('model', {})
    name = config.get('default', '') if isinstance(config, dict) else config
    provider = config.get('provider', '') if isinstance(config, dict) else ''
    provider = provider or get_active_provider()
    if not name or not provider:
        return False
    profile = get_provider_profile(provider)
    if profile and profile.auth_type == 'api_key':
        return bool(get_api_key_provider_status(provider).get('configured'))
    # OAuth/local providers perform their authoritative check in their existing setup UI.
    return None


def setup_action(stage, reasons):
    if any('登录' in reason or '接管' in reason for reason in reasons):
        return '/accounts'
    if stage == 'publish' and any('图片' in reason for reason in reasons):
        return '/materials?tab=assets'
    return '/cron?tab=plan'
