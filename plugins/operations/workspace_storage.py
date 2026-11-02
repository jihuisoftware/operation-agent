"""Enforce ownership on SQL writes, including services using direct INSERTs."""


def initialize(db, scope):
    db.execute('CREATE TABLE IF NOT EXISTS ownership(business_id TEXT NOT NULL,topic_id TEXT PRIMARY KEY)')
    db.execute('CREATE INDEX IF NOT EXISTS ownership_business ON ownership(business_id)')
    owner = db.execute('SELECT * FROM ownership').fetchone()
    if owner and tuple(owner) != (scope['business_id'], scope['id']):
        raise ValueError('主题数据库归属不匹配')
    db.execute('INSERT OR IGNORE INTO ownership VALUES (?,?)', (scope['business_id'], scope['id']))
    for table, field in (('objects', 'data'), ('events', 'data'), ('actions', 'data'), ('commands', 'payload')):
        db.execute(f"CREATE INDEX IF NOT EXISTS {table}_scope ON {table}(json_extract({field},'$.business_id'),json_extract({field},'$.topic_id'))")
        for operation in ('INSERT', 'UPDATE'):
            db.execute(f"""CREATE TRIGGER IF NOT EXISTS {table}_owner_{operation.lower()} AFTER {operation} ON {table}
                WHEN COALESCE(json_extract(NEW.{field},'$.topic_id'),'') != (SELECT topic_id FROM ownership)
                OR COALESCE(json_extract(NEW.{field},'$.business_id'),'') != (SELECT business_id FROM ownership)
                BEGIN UPDATE {table} SET {field}=json_set({field},'$.business_id',(SELECT business_id FROM ownership),
                '$.topic_id',(SELECT topic_id FROM ownership)) WHERE id=NEW.id; END""")
        if not owner:
            db.execute(f'UPDATE {table} SET {field}={field}')
