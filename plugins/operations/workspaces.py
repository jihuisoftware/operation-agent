"""Profile-owned workspace directory; topic databases are an isolation boundary.

The directory never accepts filesystem paths from clients. Existing SQL services retain
their transactional contracts inside a topic; shared account/budget arbitration lives here.
"""
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path
import json
import sqlite3
import uuid

ACTIVE_SCOPE = ContextVar('operations_scope', default=None)

SCHEMA = """
CREATE TABLE IF NOT EXISTS businesses(id TEXT PRIMARY KEY,name TEXT NOT NULL,category TEXT NOT NULL DEFAULT '',archived INTEGER NOT NULL DEFAULT 0,paused INTEGER NOT NULL DEFAULT 0,account TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS topics(id TEXT PRIMARY KEY,business_id TEXT NOT NULL REFERENCES businesses(id),name TEXT NOT NULL,file TEXT NOT NULL UNIQUE,archived INTEGER NOT NULL DEFAULT 0);
CREATE INDEX IF NOT EXISTS topics_business ON topics(business_id,archived);
CREATE TABLE IF NOT EXISTS preferences(id TEXT PRIMARY KEY,data TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS accounts(id TEXT PRIMARY KEY,identity TEXT NOT NULL DEFAULT '',conflict TEXT NOT NULL DEFAULT '',held INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS charges(id TEXT PRIMARY KEY,day TEXT NOT NULL,kind TEXT NOT NULL,amount INTEGER NOT NULL,topic_id TEXT NOT NULL,account_id TEXT NOT NULL DEFAULT '');
CREATE INDEX IF NOT EXISTS charges_day ON charges(day,kind,account_id);
CREATE TABLE IF NOT EXISTS account_claims(account_id TEXT NOT NULL,kind TEXT NOT NULL,target TEXT NOT NULL,topic_id TEXT NOT NULL,action_id TEXT NOT NULL,PRIMARY KEY(account_id,kind,target));
CREATE TABLE IF NOT EXISTS account_leases(account_id TEXT PRIMARY KEY,topic_id TEXT NOT NULL,worker TEXT NOT NULL,command_id TEXT NOT NULL,expires REAL NOT NULL);
CREATE TABLE IF NOT EXISTS account_actions(account_id TEXT NOT NULL,topic_id TEXT NOT NULL,action_id TEXT NOT NULL,kind TEXT NOT NULL,state TEXT NOT NULL,PRIMARY KEY(topic_id,action_id));
CREATE TABLE IF NOT EXISTS account_logins(account_id TEXT NOT NULL,platform TEXT NOT NULL,record TEXT NOT NULL,evidence TEXT,PRIMARY KEY(account_id,platform));
CREATE TABLE IF NOT EXISTS account_holds(account_id TEXT PRIMARY KEY,worker TEXT NOT NULL,seen REAL NOT NULL);
CREATE TABLE IF NOT EXISTS requests(id TEXT NOT NULL,topic_id TEXT NOT NULL,kind TEXT NOT NULL,state TEXT NOT NULL DEFAULT 'pending',detail TEXT NOT NULL DEFAULT '',PRIMARY KEY(topic_id,id));
CREATE TABLE IF NOT EXISTS scheduled_queue(topic_id TEXT NOT NULL,stage TEXT NOT NULL,due TEXT NOT NULL,PRIMARY KEY(topic_id,stage));
CREATE TABLE IF NOT EXISTS resources(business_id TEXT NOT NULL,kind TEXT NOT NULL,id TEXT NOT NULL,data TEXT NOT NULL,created TEXT NOT NULL,PRIMARY KEY(business_id,kind,id));
"""


class Workspaces:
    def __init__(self, root=None):
        if root is None:
            from plugins.plugin_storage import plugin_data_dir
            root = plugin_data_dir('operations')
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.path = self.root / 'workspaces.db'
        with self.connection() as db:
            if db.execute("SELECT 1 FROM sqlite_master WHERE name='topics'").fetchone() and db.execute('PRAGMA user_version').fetchone()[0] != 1:
                raise ValueError('开发数据格式已变化，请清理运营数据后重新开始')
            db.executescript(SCHEMA)
            db.execute('PRAGMA user_version=1')
            db.execute('BEGIN IMMEDIATE')
            if not db.execute('SELECT 1 FROM topics').fetchone():
                self._bootstrap(db)

    @contextmanager
    def connection(self):
        db = sqlite3.connect(self.path, timeout=30)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON')
        try:
            with db:
                yield db
        finally:
            db.close()

    def _bootstrap(self, db):
        from .policy import DEFAULT
        policy = DEFAULT
        business, topic, account = (uuid.uuid4().hex for _ in range(3))
        db.execute('INSERT INTO accounts(id) VALUES (?)', (account,))
        db.execute('INSERT INTO businesses(id,name,category,account) VALUES (?,?,?,?)', (business, '我的业务', '', account))
        db.execute('INSERT INTO topics(id,business_id,name,file) VALUES (?,?,?,?)', (topic, business, '未设置主题', f'topics/{topic}.db'))
        db.execute("INSERT INTO preferences VALUES ('limits',?)", (json.dumps({'source': policy['limits']['source'], 'model': policy['model_calls'], '_timezone': policy['timezone'], **{k: v for k, v in policy['limits'].items() if k != 'source'}}),))

    def catalog(self):
        with self.connection() as db:
            selection = db.execute("SELECT data FROM preferences WHERE id='selection'").fetchone()
            return {'businesses': [dict(r) for r in db.execute('SELECT * FROM businesses ORDER BY rowid')],
                    'topics': [dict(r) for r in db.execute('SELECT id,business_id,name,archived FROM topics ORDER BY rowid')],
                    'accounts': [dict(r) for r in db.execute('SELECT * FROM accounts')],
                    'paused': bool(db.execute("SELECT 1 FROM preferences WHERE id='paused' AND data='true'").fetchone()),
                    'selection': json.loads(selection[0]) if selection else None}

    def resolve(self, business=None, topic=None):
        if bool(business) != bool(topic):
            raise ValueError('业务与主题必须同时指定')
        with self.connection() as db:
            if not topic:
                choices = db.execute('SELECT id,business_id FROM topics WHERE archived=0').fetchall()
                if len(choices) != 1:
                    raise ValueError('请选择业务和主题，并同时传入 business_id 与 topic_id')
                topic, business = choices[0]
            row = db.execute('SELECT t.*,b.account,b.paused,b.archived AS business_archived,b.name AS business_name FROM topics t JOIN businesses b ON b.id=t.business_id WHERE t.id=? AND b.id=?', (topic, business)).fetchone()
        if not row:
            raise ValueError('业务或主题不存在于当前 Profile')
        return dict(row)

    def store(self, business=None, topic=None):
        from .store import Store
        scope = self.resolve(business, topic)
        return Store(self.root / scope['file'], workspace=self, scope=scope)

    def create(self, name, *, business=None, category='', copy_topic=None):
        name = str(name).strip()
        if not name or len(name) > 120:
            raise ValueError('名称需要 1 至 120 个字符')
        topic_id = uuid.uuid4().hex
        business_id = business or uuid.uuid4().hex
        from .workspace_topics import new_policy
        policy, category = new_policy(self, name, business, category, copy_topic)
        with self.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            if business:
                if not db.execute('SELECT 1 FROM businesses WHERE id=? AND archived=0', (business,)).fetchone():
                    raise ValueError('业务不存在或已归档')
            else:
                account = uuid.uuid4().hex
                db.execute('INSERT INTO accounts(id) VALUES (?)', (account,))
                db.execute('INSERT INTO businesses(id,name,category,account) VALUES (?,?,?,?)', (business_id, name, category, account))
            db.execute('INSERT INTO topics(id,business_id,name,file) VALUES (?,?,?,?)', (topic_id, business_id, name, f'topics/{topic_id}.db'))
        store = self.store(business_id, topic_id)
        shared = store.policy()[1]
        policy.update(knowledge=shared['knowledge'], brand=shared['brand'])
        with store.connection() as db:
            db.execute('UPDATE settings SET version=0,data=? WHERE id=1', (json.dumps(policy, ensure_ascii=False),))
            db.execute("DELETE FROM objects WHERE kind='policy'")
        from .workspace_resources import synchronize
        synchronize(store)
        return {'business_id': business_id, 'topic_id': topic_id}

    def blocked(self, scope):
        current = self.resolve(scope['business_id'], scope['id'])
        return bool(current['archived'] or current['business_archived'] or current['paused'] or self.catalog()['paused'])

    def rename(self, kind, identity, name):
        name = str(name).strip()
        if kind not in {'businesses', 'topics'} or not name or len(name) > 120:
            raise ValueError('名称或类型无效')
        if kind == 'topics':
            topic = next((t for t in self.catalog()['topics'] if t['id'] == identity), None)
            if not topic:
                raise ValueError('记录不存在')
            from .workspace_topics import rename_topic
            rename_topic(self, topic, name)
        with self.connection() as db:
            if not db.execute(f'UPDATE {kind} SET name=? WHERE id=?', (name, identity)).rowcount:
                raise ValueError('记录不存在')

    def update_state(self, kind, identity, action):
        if action not in {'pause', 'resume', 'archive'}:
            raise ValueError('未知操作')
        if kind == 'profile' and action != 'archive':
            with self.connection() as db:
                db.execute("INSERT OR REPLACE INTO preferences VALUES ('paused',?)", (json.dumps(action == 'pause'),))
            return
        entries = [t for t in self.catalog()['topics'] if (t['business_id'] if kind == 'businesses' else t['id']) == identity]
        if not entries:
            raise ValueError('记录不存在')
        for topic in entries:
            store = self.store(topic['business_id'], topic['id'])
            with store.connection() as db:
                if action == 'archive' and (db.execute("SELECT 1 FROM runs WHERE state='running'").fetchone() or db.execute("SELECT 1 FROM actions WHERE state IN ('queued','executing','submitted','unknown')").fetchone()):
                    raise ValueError('存在执行中或待核对动作，请先暂停并完成核对')
            if kind == 'topics' and action != 'archive':
                version, policy = store.policy()
                store.configure({**policy, 'paused': action == 'pause'}, version)
        if kind not in {'businesses', 'topics'}:
            raise ValueError('未知类型')
        with self.connection() as db:
            field = 'archived' if action == 'archive' else 'paused'
            if kind == 'businesses' or field == 'archived':
                db.execute(f'UPDATE {kind} SET {field}=? WHERE id=?', (int(action != 'resume'), identity))


@contextmanager
def bind_scope(business, topic):
    token = ACTIVE_SCOPE.set((business, topic))
    try:
        yield
    finally:
        ACTIVE_SCOPE.reset(token)
