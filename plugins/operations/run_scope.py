"""Durable provenance for artifacts and events produced by an operations run."""
import json


def annotate(store, data):
    result = dict(data)
    for key, value in (('run_id', store.current_run_id), ('manual_run_id', store.manual_run_id),
                       ('debug_id', getattr(store, 'debug_id', None))):
        if value:
            result.setdefault(key, value)
    return result


def runs_for_batch(db, day, batch):
    rows = [dict(row) for row in db.execute("SELECT * FROM runs WHERE day=? AND stage!='report' ORDER BY started", (day,))]
    if not batch:
        return rows
    slot = batch if batch.startswith('debug:') else 'manual:' + batch
    # Request IDs may contain underscores, so SQL LIKE would include other batches.
    return [row for row in rows if row['slot'] == slot or row['slot'].startswith(slot + ':')]


def belongs(data, batch, run_ids):
    return not batch or data.get('debug_id') == batch or data.get('manual_run_id') == batch or data.get('run_id') in run_ids


class ReportScope:
    def __init__(self, store, day):
        self.store, self.day, self.batch = store, day, store.manual_run_id
        with store.connection() as db:
            self.runs = runs_for_batch(db, day, self.batch)
            self.run_ids = {row['id'] for row in self.runs}
            self.events = [dict(row) for row in db.execute(
                "SELECT * FROM events WHERE json_extract(data,'$.day')=? "
                "OR (? IS NOT NULL AND json_extract(data,'$.day') IS NULL) ORDER BY id", (day, self.batch))
                if belongs(json.loads(row['data']), self.batch, self.run_ids)]
            self.actions = [dict(row) for row in db.execute('SELECT * FROM actions WHERE day=? ORDER BY created', (day,))
                            if belongs(json.loads(row['data']), self.batch, self.run_ids)]

    def objects(self, kind):
        return [row for row in self.store.objects(kind, self.day) if belongs(row, self.batch, self.run_ids)]


def call_count(events):
    counts = {}
    for event in events:
        if event['kind'] not in {'model_call', 'usage'}:
            continue
        run = json.loads(event['data']).get('run_id')
        group = counts.setdefault(run, {'model_call': 0, 'usage': 0})
        group[event['kind']] += 1
    # Failed attempts have no receipt; receipt-only callers still count in their own run.
    return sum(max(group.values()) for group in counts.values())
