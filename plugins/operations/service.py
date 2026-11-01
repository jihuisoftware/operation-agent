"""Human management commands; intentionally not exposed as model tools."""
import hashlib
import json
from datetime import date
import uuid
import time

from .policy import local_day, now_iso, permitted
from .store import encoded


def resolve_action(store, identity, state, evidence):
    from .action_history import resolve
    return resolve(store, identity, state, evidence)


def retry_action(store, identity):
    with store.connection() as db:
        db.execute("BEGIN IMMEDIATE")
        row = db.execute("SELECT * FROM actions WHERE id=?", (identity,)).fetchone()
        if not row or row["state"] != "confirmed_not_published":
            raise ValueError("只有人工确认未执行成功的动作才能重新执行；未知结果先核对")
        cfg = db.execute("SELECT * FROM settings WHERE id=1").fetchone()
        policy, action = json.loads(cfg["data"]), json.loads(row["data"])
        reason = permitted(policy, action)
        if reason:
            raise ValueError(reason)
        day = local_day(policy)
        count = db.execute("SELECT count(*) FROM actions WHERE day=? AND kind=? AND id!=? AND state!='cancelled'",
                           (day, row["kind"], identity)).fetchone()[0]
        if count >= policy["limits"][row["kind"]]:
            raise ValueError("达到每日额度")
        from .publication_snapshot import capture
        action = capture(db, action, cfg['version'], policy)
        db.execute('UPDATE actions SET data=? WHERE id=?', (encoded(action), identity))
        payload = {**action, "policy_version": cfg["version"]}
        db.execute("UPDATE actions SET state='queued',version=?,day=? WHERE id=?", (cfg["version"], day, identity))
        command = uuid.uuid4().hex
        kind = "publish" if row["kind"] == "publish" else "interact"
        db.execute("INSERT INTO commands VALUES (?,?,?,?,'queued',NULL,?,'{}')",
                   (command, identity, kind, encoded(payload), time.time() + 120))
    store.event("manual_retry", {"day": day, "action_id": identity, "command_id": command})
    return command


def cancel_action(store, identity):
    with store.connection() as db:
        db.execute("BEGIN IMMEDIATE")
        changed = db.execute("UPDATE actions SET state='cancelled' WHERE id=? AND state='queued'", (identity,)).rowcount
        if not changed:
            raise ValueError("动作已开始或已结束，不能假定取消成功；请暂停并核对结果")
        db.execute("UPDATE commands SET state='cancelled' WHERE action_id=? AND state='queued'", (identity,))


def revoke_asset(store, identity):
    version, policy = store.policy()
    with store.connection() as db:
        row = db.execute("SELECT data FROM objects WHERE kind='asset' AND id=?", (identity,)).fetchone()
        if not row:
            raise ValueError("素材不存在")
        data = json.loads(row[0])
        data["revoked"] = True
        db.execute("UPDATE objects SET data=? WHERE id=?", (encoded(data), identity))
    # Revoke already queued snapshots as well; in-flight workers check version before each step.
    store.configure(policy, version)
    store.event("asset_revoked", {"id": identity})


def add_record(store, kind, body):
    if kind == "metric":
        date.fromisoformat(body["day"])
        if not all(body.get(key) for key in ("id", "name", "definition", "source")):
            raise ValueError("指标需包含稳定导入 ID、日期、名称、口径和来源")
        if body.get("value") is not None and type(body["value"]) not in {int, float}:
            raise ValueError("指标值必须是数值或 null，缺失不能填零")
        return store.put(kind, body, "metric:" + body["id"])
    if kind == "content":
        from .content import validate_content
        validate_content(body, store.objects("source"), [a for a in store.objects("asset") if not a.get("revoked")])
        digest = hashlib.sha256(encoded(body).encode()).hexdigest()
        return store.put(kind, {**body, "manual": True, "day": local_day(store.policy()[1]), "created": now_iso()}, digest)
    if kind == "task":
        if not isinstance(body.get("text"), str) or not body["text"].strip():
            raise ValueError("任务不能为空")
        return store.put(kind, {**body, "day": local_day(store.policy()[1])})
    raise ValueError("不支持的业务记录")
