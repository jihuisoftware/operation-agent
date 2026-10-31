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
CREATE TABLE IF NOT EXISTS platform_logins (platform TEXT NOT NULL, worker TEXT NOT NULL, state TEXT NOT NULL,
 account_id TEXT NOT NULL, checked REAL NOT NULL, PRIMARY KEY(platform, worker));
CREATE TABLE IF NOT EXISTS platform_login_evidence (platform TEXT NOT NULL, worker TEXT NOT NULL, state TEXT NOT NULL,
 account_id TEXT NOT NULL, checked REAL NOT NULL, PRIMARY KEY(platform, worker));
INSERT OR IGNORE INTO platform_login_evidence SELECT * FROM platform_logins WHERE state IN ('logged_in','logged_out');
CREATE TABLE IF NOT EXISTS workers (id TEXT PRIMARY KEY, seen REAL NOT NULL);
CREATE TABLE IF NOT EXISTS leases (id TEXT PRIMARY KEY, token TEXT NOT NULL, expires REAL NOT NULL);
CREATE TABLE IF NOT EXISTS events (id INTEGER PRIMARY KEY, at TEXT NOT NULL, kind TEXT NOT NULL, data TEXT NOT NULL);
"""


def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False)


class Store:
    def __init__(self, path=None):
        self.path = path
        self.lease_token = None
        self.manual_run_id = None
        self.execution_id = None
        self.current_run_id = None
        with self.connection() as db:
            db.executescript(SCHEMA)
            db.execute("INSERT OR IGNORE INTO settings VALUES (1,0,?)", (encoded(DEFAULT),))
        from .migration import migrate
        with self.connection() as db:
            migrate(db)
        from .progress import sync_plan
        sync_plan(self)

    @contextmanager
    def connection(self):
        db = sqlite3.connect(self.path, timeout=15) if self.path else plugin_db("operations")
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def policy(self):
        with self.connection() as db:
            row = db.execute("SELECT * FROM settings WHERE id=1").fetchone()
            return row["version"], {**DEFAULT, **json.loads(row["data"])}

    def configure(self, value, expected_version, *, request_id=None, request_hash=None):
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
            version = expected_version + 1
            db.execute("UPDATE settings SET version=?,data=? WHERE id=1", (version, encoded(policy)))
            db.execute("UPDATE actions SET state='cancelled' WHERE state='queued'")
            db.execute("UPDATE commands SET state='cancelled' WHERE state='queued'")
            db.execute("INSERT INTO objects VALUES (?, 'policy', ?, ?)",
                       (f"policy:{version}", encoded({"version": version, "policy": policy}), now_iso()))
            db.execute("INSERT INTO events(at,kind,data) VALUES (?, 'policy', ?)",
                       (now_iso(), encoded({"version": version, "enabled": policy["enabled"], "paused": policy["paused"]})))
            if request_id:
                db.execute("INSERT INTO objects VALUES (?, 'application', ?, ?)",
                           ("apply:" + request_id, encoded({"version": version, "hash": request_hash}), now_iso()))
        from .progress import sync_plan
        sync_plan(self)
        return version

    def event(self, kind, data):
        with self.connection() as db:
            db.execute("INSERT INTO events(at,kind,data) VALUES (?,?,?)", (now_iso(), kind, encoded(data)))

    def put(self, kind, data, identity=None):
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
            self.progress("开始执行")
        return identity if changed else None

    def finish_run(self, identity, state, detail=""):
        with self.connection() as db:
            db.execute("UPDATE runs SET state=?,detail=?,ended=? WHERE id=?", (state, detail, now_iso(), identity))
        from .progress import update
        update(self, identity, state, detail)
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
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM settings WHERE id=1").fetchone()
            policy = json.loads(row["data"])
            error = permitted(policy, action)
            if error or row["version"] != version:
                raise ValueError(error or "运营规则已变更")
            day = day or local_day(policy)
            target = action["target"]
            if self.manual_run_id:
                target = f"manual:{self.manual_run_id}:{target}"
                action = {**action, "manual_run_id": self.manual_run_id}
            elif db.execute("SELECT 1 FROM actions WHERE kind=? AND json_extract(data,'$.target')=? AND json_extract(data,'$.account_id')=?",
                            (action["kind"], target, action["account_id"])).fetchone():
                return None
            scoped_target = encoded([action["account_id"], target])
            identity = hashlib.sha256(encoded([action["kind"], action["account_id"], target]).encode()).hexdigest()
            # Match the durable target too, so pre-account-scoped IDs stay idempotent.
            if db.execute("SELECT 1 FROM actions WHERE kind=? AND target IN (?,?) AND json_extract(data,'$.account_id')=?",
                          (action["kind"], target, scoped_target, action["account_id"])).fetchone():
                return None
            if db.execute("SELECT 1 FROM actions WHERE kind=? AND state IN ('unknown','submitted','executing','queued')", (action["kind"],)).fetchone():
                raise ValueError("同类动作仍有未核对结果，请先处理异常")
            count = db.execute("SELECT count(*) FROM actions WHERE day=? AND kind=? AND state!='cancelled'",
                               (day, action["kind"])).fetchone()[0]
            if count >= policy["limits"][action["kind"]]:
                raise ValueError("达到每日动作额度")
            changed = db.execute("INSERT OR IGNORE INTO actions VALUES (?,?,?,?,?,'queued',?,'{}',?)",
                (identity, day, version, action["kind"], scoped_target, encoded(action), now_iso())).rowcount
            return identity if changed else None

    def blocked(self, kind, version):
        return any(b["kind"] == kind and b["version"] == version for b in self.objects("block"))

    def enqueue(self, kind, payload, action_id=None):
        identity = uuid.uuid4().hex
        version, _ = self.policy()
        if self.blocked(payload.get("kind", kind), version):
            raise ValueError("该能力已暂停，请处理异常并重新保存规则后恢复")
        payload = {**payload, "policy_version": version}
        with self.connection() as db:
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
            if busy or cfg["paused"] or not cfg["enabled"]:
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
                db.execute("UPDATE actions SET state='executing' WHERE id=?", (row["action_id"],))
            db.execute("UPDATE commands SET state='running',worker=? WHERE id=?", (worker, row["id"]))
            return {"id": row["id"], "kind": row["kind"], "payload": json.loads(row["payload"]), "expires": row["expires"]}

    def _expire(self, db):
        db.execute("UPDATE actions SET state='blocked' WHERE id IN (SELECT action_id FROM commands WHERE state='queued' AND expires<?)", (time.time(),))
        db.execute("UPDATE actions SET state='unknown' WHERE id IN (SELECT action_id FROM commands WHERE state='running' AND expires<?)", (time.time(),))
        db.execute("UPDATE commands SET state='unknown' WHERE state IN ('running','queued') AND expires<?", (time.time(),))

    def acknowledge(self, identity, worker, result):
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            self._expire(db)
            row = db.execute("SELECT * FROM commands WHERE id=? AND worker=? AND state='running'", (identity, worker)).fetchone()
            if not row:
                raise ValueError("任务已过期或执行者不匹配，请核对执行结果")
            db.execute("UPDATE commands SET state='done',result=? WHERE id=?", (encoded(result), identity))
            if result.get("state") == "blocked":
                payload = json.loads(row["payload"])
                block = {"kind": payload.get("kind", row["kind"]), "version": payload["policy_version"], "error": result.get("error"), "day": local_day(self.policy()[1])}
                db.execute("INSERT OR IGNORE INTO objects VALUES (?, 'block', ?, ?)",
                           (f"block:{block['version']}:{block['kind']}", encoded(block), now_iso()))
            if row["action_id"]:
                state = result.get("state", "unknown")
                if state not in {"published", "submitted", "confirmed", "failed", "unknown", "blocked"}:
                    state = "unknown"
                if state in {"published", "confirmed"} and not result.get("evidence"):
                    state = "unknown"
                db.execute("UPDATE actions SET state=?,result=? WHERE id=?", (state, encoded(result), row["action_id"]))

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
        return self.put("asset", {"name": Path(filename).name, "file": digest + suffix,
                                  "authorized": True, "sha256": digest}, digest)
