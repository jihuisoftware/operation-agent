"""New policy defaults must not look like user edits in an existing collection ledger."""
import json

import pytest

from plugins.operations import collection, collection_ledger
from plugins.operations.policy import DEFAULT
from plugins.operations.store import encoded
from tests.plugins.test_operations_collection import setup


@pytest.mark.parametrize('missing', ['image_mode', 'brand'])
def test_legacy_policy_collects_with_effective_defaults_without_rewriting_settings(tmp_path, monkeypatch, missing):
    store, _, web = setup(tmp_path, monkeypatch)
    with store.connection() as db:
        raw = json.loads(db.execute('SELECT data FROM settings WHERE id=1').fetchone()[0])
        raw.pop(missing)
        db.execute('UPDATE settings SET data=? WHERE id=1', (encoded(raw),))
    version, effective = store.policy()
    assert effective[missing] == DEFAULT[missing]
    calls = []
    async def extract(urls, **_):
        calls.append(urls)
        return json.dumps({'results': [{'title': '收纳指南', 'content': '先按使用频率分类，再标注物品位置。'}]})
    monkeypatch.setattr(web, 'web_extract_tool', extract)
    result = collection.collect(store, effective, '2026-11-09')
    assert result['succeeded'] == 1 and result['used'] == 1 and len(calls) == 1
    with store.connection() as db:
        saved = db.execute('SELECT version,data FROM settings WHERE id=1').fetchone()
    assert saved['version'] == version and json.loads(saved['data']) == raw


@pytest.mark.parametrize('field,value', [('keywords', ['新的检索方向']), ('paused', True)])
def test_real_change_between_precheck_and_reservation_still_stops_without_charging(tmp_path, monkeypatch, field, value):
    store, policy, _ = setup(tmp_path, monkeypatch)
    check = collection_ledger.check
    def change_after_check(current, snapshot):
        check(current, snapshot)
        with current.connection() as db:
            updated = json.loads(db.execute('SELECT data FROM settings WHERE id=1').fetchone()[0])
            updated[field] = value
            db.execute('UPDATE settings SET data=? WHERE id=1', (encoded(updated),))
    monkeypatch.setattr(collection_ledger, 'check', change_after_check)
    with pytest.raises(ValueError, match='运营规则变更，停止采集'):
        collection_ledger.reserve(store, policy, '2026-11-09', 'https://example.org/a')
    assert collection_ledger.budget(store, '2026-11-09') == 0
    assert not store.objects('collection_attempt')
