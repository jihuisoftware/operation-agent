"""Complete source text and bounded organization preserve omitted sections and resume work."""
from copy import deepcopy
import json

from plugins.operations import collection, organization
from plugins.operations.policy import DEFAULT, local_day
from plugins.operations.store import Store
from tests.plugins.operations_support import organized_response


def configured(tmp_path, monkeypatch):
    monkeypatch.setenv('HERMES_HOME', str(tmp_path))
    store = Store(tmp_path / 'documents.db')
    policy = deepcopy(DEFAULT)
    policy.update(enabled=True, topic='工程', goal='准确提炼')
    policy['modules'].update(research=True, organize=True)
    store.configure(policy, 0)
    return store, policy, local_day(policy)


def test_collect_and_organize_complete_article_without_login_boilerplate(tmp_path, monkeypatch):
    store, policy, day = configured(tmp_path, monkeypatch)
    article = '## 原则一\n' + '工程正文。' * 1600 + '\n## 原则四：反馈循环\n## 原则五：错误分析\n## 原则六：系统问题\n'
    shell = '\n其他扫码方式：微信\n下载知乎App\n验证码登录\n密码登录\n获取短信验证码\n关闭二维码\n'
    async def extract(urls, **kwargs):
        assert kwargs['char_limit'] == 500000
        return json.dumps({'results': [{'url': urls[0], 'content': article + shell * 3, 'truncated': False, 'original_chars': len(article + shell * 3)}]})
    monkeypatch.setattr('tools.web_tools.web_extract_tool', extract)
    source = collection.read(store, policy, day, 'https://example.org/a', {}, 1, None, {})
    assert '原则六' in source['text'] and '获取短信验证码' not in source['text']
    assert source['raw_text'] == article + shell * 3
    captured = []
    monkeypatch.setattr(organization, 'generate', lambda *args: captured.append(args[-1]) or organized_response(args[-1]))
    result = organization.organize(store, policy, day, 1)
    assert result['organized'] == 1
    assert '原则六' in captured[0]['sources'][0]['text']
    assert captured[0]['sources'][0]['text_truncated'] is False
    article = ''
    empty = collection.read(store, policy, day, 'https://example.org/login', {}, 1, None, {})
    assert empty['state'] == 'unavailable' and not empty['text'] and empty['error']


def test_long_source_resumes_segments_and_does_not_publish_partial_organization(tmp_path, monkeypatch):
    store, policy, day = configured(tmp_path, monkeypatch)
    policy['model_calls'] = 1
    store.configure(policy, 1)
    store.put('source', {'day': day, 'scope_topic': policy['topic'], 'title': '长篇', 'url': 'https://example.org/long',
                        'text': '\n\n'.join(f'## 第{i}章\n' + str(i) * 5000 for i in range(6)), 'state': 'read'}, 'long')
    calls = []
    monkeypatch.setattr(organization, 'generate', lambda *args: calls.append(args[-1]) or organized_response(args[-1]))
    first = organization.organize(store, policy, day, 2)
    assert first['pending'] == 1 and not store.objects('organized_source')
    first_ids = {row['id'] for row in calls[0]['sources']}
    policy['model_calls'] = 10
    store.configure(policy, 2)
    organization.organize(store, policy, day, 3)
    assert len(store.objects('organized_source')) == 1
    later_segment_ids = {row['id'] for call in calls[1:] if call['task'] != 'organize_merge' for row in call['sources']}
    assert not first_ids & later_segment_ids
    assert store.objects('organized_source')[0]['coverage']['complete'] is True
    assert all(len(json.dumps(call, ensure_ascii=False, sort_keys=True)) <= 24000 for call in calls)


def test_old_incomplete_sources_repair_with_read_budget_and_preserve_revision(tmp_path, monkeypatch):
    store, policy, day = configured(tmp_path, monkeypatch)
    policy['limits']['source'] = 1
    store.configure(policy, 1)
    for index in range(2):
        store.put('source', {'day': '2026-11-01', 'scope_topic': policy['topic'], 'title': '旧资料', 'url': f'https://example.org/{index}',
                            'text': '旧截断内容', 'truncated': True, 'state': 'read'}, str(index))
    store.put('report', {'day': '2026-11-01', 'markdown': '旧日报快照'}, 'old-report')
    fetched = []
    async def extract(urls, **kwargs):
        fetched.extend(urls)
        return json.dumps({'results': [{'url': urls[0], 'content': '完整正文包含原则四五六', 'truncated': False}]})
    monkeypatch.setattr('tools.web_tools.web_extract_tool', extract)
    monkeypatch.setattr(organization, 'generate', lambda *args: organized_response(args[-1]))
    outcome = organization.organize(store, policy, day, 2)
    assert len(fetched) == 1 and outcome['organized'] == 1 and outcome['pending'] == 1
    archive = store.objects('source_revision')[0]
    assert archive['text'] == '旧截断内容' and archive['truncated'] is True
    assert store.objects('report')[0]['markdown'] == '旧日报快照'
    assert all(row['day'] == '2026-11-01' for row in store.objects('source'))


def test_many_segment_summaries_reduce_in_bounded_checkpointed_requests(tmp_path, monkeypatch):
    store, policy, day = configured(tmp_path, monkeypatch)
    store.put('source', {'day': day, 'scope_topic': policy['topic'], 'title': '完整长文', 'url': 'https://example.org/large',
                        'text': '\n\n'.join(f'## 第{i}段\n' + '正文' * 2500 for i in range(30)), 'state': 'read'}, 'large')
    requests = []
    def model(*args):
        data = args[-1]
        requests.append(data)
        result = organized_response(data)
        for item in result['items']:
            item.update(summary='摘要' * 500, facts=['事实' * 200] * 3, uncertainties=['边界' * 100])
        return result
    monkeypatch.setattr(organization, 'generate', model)
    result = organization.organize(store, policy, day, 1)
    assert result['organized'] == 1 and result['pending'] == 0
    assert sum(data['task'] == 'organize_merge' for data in requests) > 1
    assert all(len(json.dumps(data, ensure_ascii=False, sort_keys=True)) <= 24000 for data in requests)
    count = len(requests)
    organization.organize(store, policy, day, 1)
    assert len(requests) == count
