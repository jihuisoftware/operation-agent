"""Profile-local SQLite ledger. Every claim/limit/lease change is transactional."""
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import sqlite3
import time
import uuid

from plugins.plugin_storage import plugin_db
from .policy import DEFAULT, local_day, now_iso, permitted, validate_policy

SCHEMA = """
CREATE TABLE IF NOT EXISTS settings (id INTEGER PRIMARY KEY CHECK(id=1), version INTEGER NOT NULL, data TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS objects (id TEXT PRIMARY KEY, kind TEXT NOT NULL, data TEXT NOT NULL, created TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS runs (id TEXT PRIMARY KEY, day TEXT NOT NULL, stage TEXT NOT NULL, slot TEXT NOT NULL,
 version INTEGER NOT NULL, state TEXT NOT NULL, detail TEXT NOT NULL, started TEXT NOT NULL, ended TEXT,
 UNIQUE(day, stage, slot));
CREATE TABLE IF NOT EXISTS actions (id TEXT PRIMARY KEY, day TEXT NOT NULL, version INTEGER NOT NULL,
 kind TEXT NOT NULL, target TEXT NOT NULL, state TEXT NOT NULL, data TEXT NOT NULL, result TEXT NOT NULL,
 created TEXT NOT NULL, UNIQUE(kind, target));
CREATE TABLE IF NOT EXISTS commands (id TEXT PRIMARY KEY, action_id TEXT, kind TEXT NOT NULL, payload TEXT NOT NULL,
 state TEXT NOT NULL, worker TEXT, expires REAL NOT NULL, result TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS commands_action ON commands(action_id);
CREATE TABLE IF NOT EXISTS platform_logins (platform TEXT NOT NULL, worker TEXT NOT NULL, state TEXT NOT NULL,
 account_id TEXT NOT NULL, checked REAL NOT NULL, PRIMARY KEY(platform, worker));
CREATE TABLE IF NOT EXISTS platform_login_evidence (platform TEXT NOT NULL, worker TEXT NOT NULL, state TEXT NOT NULL,
 account_id TEXT NOT NULL, checked REAL NOT NULL, PRIMARY KEY(platform, worker));
CREATE TABLE IF NOT EXISTS workers (id TEXT PRIMARY KEY, seen REAL NOT NULL);
CREATE TABLE IF NOT EXISTS leases (id TEXT PRIMARY KEY, token TEXT NOT NULL, expires REAL NOT NULL);
CREATE TABLE IF NOT EXISTS events (id INTEGER PRIMARY KEY, at TEXT NOT NULL, kind TEXT NOT NULL, data TEXT NOT NULL);
"""


def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False)


class Store:
    def __init__(self, path=None, *, workspace=None, scope=None):
        if path is None:
            from .workspaces import ACTIVE_SCOPE, Workspaces
            workspace = Workspaces()
            scope = workspace.resolve(*(ACTIVE_SCOPE.get() or (None, None)))
            path = workspace.root / scope['file']
        self.workspace, self.scope = workspace, scope
        self.path = Path(path) if path else None
        if self.path:
            self.path.parent.mkdir(parents=True, exist_ok=True)
        self.lease_token = None
        self.manual_run_id = None
        self.run_options = None
        self.execution_id = None
        self.current_run_id = None
        with self.connection() as db:
            db.executescript(SCHEMA)
            from .business_store import initialize as initialize_business
            initialize_business(db)
            db.execute("INSERT OR IGNORE INTO settings VALUES (1,0,?)", (encoded(DEFAULT),))
            if json.loads(db.execute('SELECT data FROM settings WHERE id=1').fetchone()[0]).get('schema_version') != 5:
                raise ValueError('不支持旧运营规则，请清理开发数据后重新开始')
            if self.scope:
                from .workspace_storage import initialize as initialize_workspace
                initialize_workspace(db, self.scope)
        from .progress import sync_plan
        from .workspace_resources import synchronize
        synchronize(self)
        sync_plan(self)

    @contextmanager
    def connection(self):
        db = sqlite3.connect(self.path, timeout=15) if self.path else plugin_db("operations")
        db.row_factory = sqlite3.Row
        if self.workspace:
            db.execute('ATTACH DATABASE ? AS directory', (str(self.workspace.path),))
        try:
            with db:
                yield db
        finally:
            db.close()

    def policy(self):
        with self.connection() as db:
            row = db.execute("SELECT * FROM settings WHERE id=1").fetchone()
            return row["version"], {**DEFAULT, **json.loads(row["data"])}

    def configure(self, value, expected_version, *, request_id=None, request_hash=None, first_run=None, activation=False):
        if self.workspace and (self.scope['archived'] or self.scope['business_archived']):
            raise ValueError('已归档主题配置为只读')
        policy = validate_policy(value)
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            if request_id:
                saved = db.execute("SELECT data FROM objects WHERE id=?", ("apply:" + request_id,)).fetchone()
                if saved:
                    receipt = json.loads(saved[0])
                    if receipt["hash"] != request_hash:
                        raise ValueError("同一请求 ID 不能用于不同配置")
                    return receipt["version"]
            row = db.execute("SELECT version FROM settings WHERE id=1").fetchone()
            if row[0] != expected_version:
                raise ValueError("配置已变更，请刷新后重新保存")
            if self.workspace:
                previous = json.loads(db.execute('SELECT data FROM settings WHERE id=1').fetchone()[0])
                if previous['topic'] != policy['topic']:
                    from .workspace_topics import rename_metadata
                    rename_metadata(db, previous['topic'], policy['topic'])
                if db.execute('SELECT count(*) FROM directory.topics WHERE archived=0').fetchone()[0] == 1:
                    db.execute("UPDATE directory.preferences SET data=? WHERE id='limits'", (encoded({**policy['limits'], 'model': policy['model_calls'], '_timezone': policy['timezone']}),))
            first_activation = activation and not db.execute("SELECT 1 FROM objects WHERE kind='policy' AND json_extract(data,'$.policy.enabled')=1").fetchone()
            if first_activation:
                db.execute("INSERT OR REPLACE INTO objects VALUES ('plan-activation','activation',?,?)", (encoded({'after': now_iso()}), now_iso()))
            version = expected_version + 1
            from .workspace_resources import save_policy
            save_policy(self, db, policy)
            db.execute("UPDATE settings SET version=?,data=? WHERE id=1", (version, encoded(policy)))
            db.execute("UPDATE actions SET state='cancelled' WHERE state='queued'")
            db.execute("UPDATE commands SET state='cancelled' WHERE state='queued'")
            from .workspace_execution import sync_actions
            sync_actions(self, db)
            db.execute("INSERT INTO objects VALUES (?, 'policy', ?, ?)",
                       (f"policy:{version}", encoded({"version": version, "policy": policy}), now_iso()))
            db.execute("INSERT INTO events(at,kind,data) VALUES (?, 'policy', ?)",
                       (now_iso(), encoded({"version": version, "enabled": policy["enabled"], "paused": policy["paused"]})))
            if request_id:
                db.execute("INSERT INTO objects VALUES (?, 'application', ?, ?)",
                           ("apply:" + request_id, encoded({"version": version, "hash": request_hash}), now_iso()))
            if first_run is not None:
                db.execute("INSERT INTO objects VALUES (?, 'quick_run', ?, ?)",
                           ('quick:' + request_id, encoded({'version': version, 'options': first_run, 'activation_boundary': first_activation, 'state': 'pending', 'created': now_iso()}), now_iso()))
        from .progress import sync_plan
        sync_plan(self)
        if self.workspace:
            with self.workspace.connection() as db:
                db.execute('UPDATE topics SET name=? WHERE id=?', (policy['topic'] or '未设置主题', self.scope['id']))
        return version

    def event(self, kind, data):
        if self.scope:
            data = {**data, 'business_id': self.scope['business_id'], 'topic_id': self.scope['id']}
        with self.connection() as db:
            db.execute("INSERT INTO events(at,kind,data) VALUES (?,?,?)", (now_iso(), kind, encoded(data)))

    def put(self, kind, data, identity=None):
        if self.scope:
            data = {**data, 'business_id': self.scope['business_id'], 'topic_id': self.scope['id']}
        identity = identity or uuid.uuid4().hex
        with self.connection() as db:
            changed = db.execute("INSERT OR IGNORE INTO objects VALUES (?,?,?,?)", (identity, kind, encoded(data), now_iso())).rowcount
        if changed and self.current_run_id:
            from .progress import saved
            saved(self, kind, identity, data)
        return identity

    def objects(self, kind, day=None):
        with self.connection() as db:
            return [{**json.loads(r["data"]), "id": r["id"]} for r in db.execute(
                "SELECT * FROM objects WHERE kind=? AND (? IS NULL OR json_extract(data,'$.day')=?) ORDER BY created DESC",
                (kind, day, day))]

    def start_run(self, day, stage, slot, version):
        identity = uuid.uuid4().hex
        with self.connection() as db:
            changed = db.execute("INSERT OR IGNORE INTO runs VALUES (?,?,?,?,?,'running','',?,NULL)",
                                 (identity, day, stage, slot, version, now_iso())).rowcount
        if changed:
            self.current_run_id = identity
            from .usage_context import begin
            begin(self, identity)
            self.progress("开始执行")
        return identity if changed else None

    def finish_run(self, identity, state, detail=""):
        with self.connection() as db:
            db.execute("UPDATE runs SET state=?,detail=?,ended=? WHERE id=?", (state, detail, now_iso(), identity))
        from .progress import update
        update(self, identity, state, detail)
        from .usage_context import finish
        finish(self, identity, state)
        self.current_run_id = None

    def progress(self, detail, data=None):
        if self.current_run_id:
            from .progress import update
            update(self, self.current_run_id, "running", detail, data)

    def lease(self, token, ttl=1800):
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM leases WHERE id='account'").fetchone()
            if row and row["expires"] > time.time():
                return False
            db.execute("INSERT OR REPLACE INTO leases VALUES ('account',?,?)", (token, time.time() + ttl))
            db.execute("UPDATE runs SET state='interrupted',detail='执行进程中断，外部动作需核对' WHERE state='running'")
            self.lease_token = token
            return True

    def renew(self):
        if self.lease_token is None:
            return
        with self.connection() as db:
            changed = db.execute("UPDATE leases SET expires=? WHERE id='account' AND token=? AND expires>?",
                                 (time.time() + 1800, self.lease_token, time.time())).rowcount
            if not changed:
                raise ValueError("账号执行租约已过期，停止旧执行进程")

    def release(self, token):
        with self.connection() as db:
            db.execute("DELETE FROM leases WHERE id='account' AND token=?", (token,))
        self.lease_token = None

    def reserve_action(self, action, version, day=None):
        from .browser_evidence import command_context
        action = {**action, **command_context(self)}
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM settings WHERE id=1").fetchone()
            policy = json.loads(row["data"])
            from .readiness import web_held
            if web_held(db):
                raise ValueError("网页正在人工接管")
            error = permitted(policy, action)
            if error or row["version"] != version:
                raise ValueError(error or "运营规则已变更")
            if db.execute("SELECT 1 FROM objects WHERE kind='block' AND json_extract(data,'$.kind')=? AND json_extract(data,'$.version')=?",
                          (action["kind"], version)).fetchone():
                raise ValueError("该能力已暂停，请处理异常并重新保存规则后恢复")
            day = day or local_day(policy)
            from .analysis_publication import check
            check(db, action, policy, day)
            target = action["target"]
            if self.manual_run_id:
                target = f"manual:{self.manual_run_id}:{target}"
                action = {**action, "manual_run_id": self.manual_run_id}
            elif db.execute("SELECT 1 FROM actions WHERE kind=? AND json_extract(data,'$.target')=? AND json_extract(data,'$.account_id')=?",
                            (action["kind"], target, action["account_id"])).fetchone():
                return None
            scoped_target = encoded([action["account_id"], target])
            identity = hashlib.sha256(encoded([action["kind"], action["account_id"], target]).encode()).hexdigest()
            if db.execute("SELECT 1 FROM actions WHERE kind=? AND target=? AND json_extract(data,'$.account_id')=?",
                          (action["kind"], scoped_target, action["account_id"])).fetchone():
                return None
            if db.execute("SELECT 1 FROM actions WHERE kind=? AND state IN ('unknown','submitted','executing','queued')", (action["kind"],)).fetchone():
                raise ValueError("同类动作仍有未核对结果，请先处理异常")
            count = db.execute("SELECT count(*) FROM actions WHERE day=? AND kind=? AND state!='cancelled'",
                               (day, action["kind"])).fetchone()[0]
            if count >= policy["limits"][action["kind"]]:
                raise ValueError("达到每日动作额度")
            from .publication_snapshot import capture
            action = capture(db, action, version, policy)
            from .workspace_execution import reserve_action
            if not reserve_action(self, db, action, identity, day):
                return None
            if self.scope:
                action = {**action, 'business_id': self.scope['business_id'], 'topic_id': self.scope['id']}
            changed = db.execute("INSERT OR IGNORE INTO actions VALUES (?,?,?,?,?,'queued',?,'{}',?)",
                (identity, day, version, action["kind"], scoped_target, encoded(action), now_iso())).rowcount
            if changed:
                kind = "publish" if action["kind"] == "publish" else "interact"
                db.execute("INSERT INTO commands VALUES (?,?,?,?,'queued',NULL,?,'{}')",
                           (uuid.uuid4().hex, identity, kind, encoded({**action, "policy_version": version}), time.time() + 120))
            return identity if changed else None

    def blocked(self, kind, version):
        return any(b["kind"] == kind and b["version"] == version for b in self.objects("block"))

    def enqueue(self, kind, payload, action_id=None):
        from .browser_evidence import command_context
        if action_id:
            with self.connection() as db:
                row = db.execute("SELECT id FROM commands WHERE action_id=? AND kind=? ORDER BY rowid DESC LIMIT 1",
                                 (action_id, kind)).fetchone()
            if not row:
                raise ValueError("动作缺少原子入队记录，请核对后重新发起")
            return row["id"]
        identity = uuid.uuid4().hex
        version, _ = self.policy()
        if self.blocked(payload.get("kind", kind), version):
            raise ValueError("该能力已暂停，请处理异常并重新保存规则后恢复")
        payload = {**command_context(self), **payload, "policy_version": version}
        with self.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            from .readiness import web_held
            from .outcomes import StageSkipped
            if web_held(db):
                raise StageSkipped('网页正在人工接管，自动网页操作已暂停')
            db.execute("INSERT INTO commands VALUES (?,?,?,?,'queued',NULL,?,'{}')",
                       (identity, action_id, kind, encoded(payload), time.time() + 120))
        return identity

    def claim(self, worker, busy=False):
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("INSERT OR REPLACE INTO workers VALUES (?,?)", (worker, time.time()))
            self._expire(db)
            policy = db.execute("SELECT * FROM settings WHERE id=1").fetchone()
            cfg = json.loads(policy["data"])
            from .readiness import web_held
            if busy or web_held(db) or cfg["paused"] or not cfg["enabled"]:
                return None
            if db.execute("SELECT 1 FROM commands WHERE state='running'").fetchone():
                return None
            row = db.execute("SELECT * FROM commands WHERE state='queued' ORDER BY rowid LIMIT 1").fetchone()
            if not row:
                return None
            if row["action_id"]:
                action = db.execute("SELECT * FROM actions WHERE id=?", (row["action_id"],)).fetchone()
                if action["version"] != policy["version"] or action["state"] != "queued":
                    db.execute("UPDATE commands SET state='cancelled' WHERE id=?", (row["id"],))
                    return None
            from .workspace_execution import claim_account
            if not claim_account(self, db, row, worker):
                return None
            if row["action_id"]:
                db.execute("UPDATE actions SET state='executing' WHERE id=?", (row["action_id"],))
            db.execute("UPDATE commands SET state='running',worker=? WHERE id=?", (worker, row["id"]))
            if row['kind'] == 'verify':
                from .review_queue import mark_running
                mark_running(db, row)
            return {"id": row["id"], "kind": row["kind"], "payload": json.loads(row["payload"]), "expires": row["expires"]}

    def _expire(self, db):
        from .review_queue import accept
        expired = db.execute("SELECT * FROM commands WHERE kind='verify' AND state IN ('queued','running') AND expires<?", (time.time(),)).fetchall()
        for command in expired:
            accept(db, command, {'state': 'unknown', 'error': '只读核对超时', 'evidence': '等待重新连接后核对'})
        db.execute("UPDATE actions SET state='blocked' WHERE id IN (SELECT action_id FROM commands WHERE state='queued' AND expires<?)", (time.time(),))
        db.execute("UPDATE actions SET state='unknown' WHERE id IN (SELECT action_id FROM commands WHERE state='running' AND expires<?)", (time.time(),))
        db.execute("UPDATE commands SET state='unknown' WHERE state IN ('running','queued') AND expires<?", (time.time(),))
        from .workspace_execution import sync_actions
        sync_actions(self, db)

    def acknowledge(self, identity, worker, result):
        from .publication_status import normalize
        result = normalize(result)
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            self._expire(db)
            row = db.execute("SELECT * FROM commands WHERE id=? AND worker=? AND state='running'", (identity, worker)).fetchone()
            if not row:
                from .late_receipts import recover
                row = recover(db, identity, worker, result)
            if not row:
                duplicate = db.execute("SELECT result FROM commands WHERE id=? AND worker=? AND state='done'", (identity, worker)).fetchone()
                from .late_receipts import same
                if duplicate and same(duplicate[0], result):
                    return
                raise ValueError("任务已过期或执行者不匹配，请核对执行结果")
            db.execute("UPDATE commands SET state='done',result=? WHERE id=?", (encoded(result), identity))
            from .workspace_execution import release_account
            release_account(self, db, identity, worker)
            if result.get("state") == "blocked" and row["kind"] not in {"verify", "account"}:
                payload = json.loads(row["payload"])
                block = {"kind": payload.get("kind", row["kind"]), "version": payload["policy_version"], "error": result.get("error"), "day": local_day(self.policy()[1])}
                db.execute("INSERT OR IGNORE INTO objects VALUES (?, 'block', ?, ?)",
                           (f"block:{block['version']}:{block['kind']}", encoded(block), now_iso()))
            if row['kind'] == 'verify':
                from .review_queue import accept
                accept(db, row, result)
            if row["action_id"]:
                state = result.get("state", "unknown")
                if state not in {"published", "submitted", "confirmed", "failed", "unknown", "blocked"}:
                    state = "unknown"
                if state in {"published", "confirmed"} and not result.get("evidence"):
                    state = "unknown"
                db.execute("UPDATE actions SET state=?,result=? WHERE id=?", (state, encoded(result), row["action_id"]))
                if state in {'submitted', 'unknown'}:
                    from .review_queue import schedule, queue
                    schedule(db, row['action_id'], result, initial=True)
                    action = db.execute('SELECT * FROM actions WHERE id=?', (row['action_id'],)).fetchone()
                    version = db.execute('SELECT version FROM settings WHERE id=1').fetchone()[0]
                    queue(db, action, version)
            from .workspace_execution import sync_actions
            sync_actions(self, db)

        if row['kind'] == 'account' and result.get('account_id'):
            from .workspace_execution import observe_account
            observe_account(self, {'platform': 'xiaohongshu', 'state': 'logged_in', 'worker': worker, 'account_id': result['account_id']})

    def command(self, identity):
        with self.connection() as db:
            self._expire(db)
            row = db.execute("SELECT * FROM commands WHERE id=?", (identity,)).fetchone()
            return {**dict(row), "result": json.loads(row["result"])}

    def snapshot(self):
        version, policy = self.policy()
        with self.connection() as db:
            tables = {name: [dict(r) for r in db.execute(f"SELECT * FROM {name} ORDER BY rowid DESC LIMIT 100")]
                      for name in ("runs", "actions", "events")}
            online = bool(db.execute("SELECT 1 FROM workers WHERE seen>?", (time.time() - 15,)).fetchone())
        tables["actions"] = [{**a, "target": json.loads(a["data"])["target"]} for a in tables["actions"]]
        if self.scope:
            owner = {'business_id': self.scope['business_id'], 'topic_id': self.scope['id']}
            tables = {name: [{**row, **owner} for row in rows] for name, rows in tables.items()}
        return {"version": version, "policy": policy, "online": online, **tables,
                **{kind: self.objects(kind)[:100] for kind in ("source", "asset", "content", "metric", "report", "task", "inbox", "brief", "block", "review")}}

    def add_asset(self, filename, content, authorized):
        from plugins.plugin_storage import plugin_data_dir
        if not authorized or not content or len(content) > 20 * 1024 * 1024:
            raise ValueError("素材必须确认使用授权，且文件不超过 20 MB")
        digest = hashlib.sha256(content).hexdigest()
        suffix = Path(filename).suffix.lower()
        if suffix not in {".png", ".jpg", ".jpeg", ".webp"}:
            raise ValueError("首版支持 PNG、JPEG、WebP 图片")
        from io import BytesIO
        from PIL import Image
        try:
            with Image.open(BytesIO(content)) as picture:
                if picture.format not in {"PNG", "JPEG", "WEBP"} or picture.width * picture.height > 40_000_000:
                    raise ValueError("图片格式不支持或像素数量超过 4000 万")
                expected = {".png": "PNG", ".jpg": "JPEG", ".jpeg": "JPEG", ".webp": "WEBP"}[suffix]
                if picture.format != expected:
                    raise ValueError("图片扩展名与实际格式不一致")
                picture.verify()
        except (OSError, Image.DecompressionBombError) as exc:
            raise ValueError("无法验证图片文件") from exc
        directory = plugin_data_dir("operations") / "assets"
        directory.mkdir(exist_ok=True)
        (directory / (digest + suffix)).write_bytes(content)
        identity = self.put("asset", {"name": Path(filename).name, "file": digest + suffix,
                                     "authorized": True, "sha256": digest}, digest)
        from .workspace_resources import save_asset
        save_asset(self, identity)
        return identity
