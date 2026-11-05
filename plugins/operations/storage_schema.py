"""Inspect existing SQLite structures without turning every status read into a writer."""
import json
import re


def names(db, namespace='main'):
    if namespace not in {'main', 'directory'}:
        raise ValueError('未知运营数据库')
    return {row[0] for row in db.execute(f'SELECT name FROM {namespace}.sqlite_master')}


def ready(db, schema, namespace='main'):
    expected = set(re.findall(r'CREATE\s+(?:UNIQUE\s+)?(?:TABLE|INDEX|TRIGGER)\s+IF\s+NOT\s+EXISTS\s+(?:\w+\.)?(\w+)', schema, re.IGNORECASE))
    return expected <= names(db, namespace)


def initialize_topic(store):
    from .store import SCHEMA, DEFAULT, encoded
    from .business_store import SCHEMA as BUSINESS_SCHEMA
    from .workspace_storage import ready as ownership_ready, initialize as initialize_ownership
    with store.connection() as db:
        complete = ready(db, SCHEMA + BUSINESS_SCHEMA)
        owned = not store.scope or ownership_ready(db, store.scope)
        if not complete:
            db.executescript(SCHEMA + BUSINESS_SCHEMA)
        row = db.execute('SELECT data FROM settings WHERE id=1').fetchone()
        if not row:
            db.execute('INSERT OR IGNORE INTO settings VALUES (1,0,?)', (encoded(DEFAULT),))
            row = db.execute('SELECT data FROM settings WHERE id=1').fetchone()
        if json.loads(row[0]).get('schema_version') != 5:
            raise ValueError('不支持旧运营规则，请清理开发数据后重新开始')
        if not owned:
            initialize_ownership(db, store.scope)
