"""Structured provider boundary shared by operations workflow tests."""


def organized_response(data):
    return {'items': [{'source_id': s['id'], 'category': '方法教程', 'relevant': True,
                       'summary': '来源方法摘要', 'facts': ['原文记录的方法'], 'opinions': [],
                       'uncertainties': ['尚未独立核实'], 'keywords': ['方法']} for s in data['sources']]}


def prepare_materials(store, policy, day, monkeypatch):
    from plugins.operations import organization
    with monkeypatch.context() as scoped:
        scoped.setattr(organization, 'generate', lambda *args: organized_response(args[-1]))
        return organization.organize(store, policy, day, store.policy()[0])


def industry_response(data):
    return {'findings': [{'view': 'content', 'dimension': '需求', 'title': '关注具体使用需求', 'text': '样本提示可验证这一方向',
                         'evidence_ids': [data['evidence'][0]['id']], 'scope': '本次样本', 'counter': '未找到反向证据', 'unknowns': '不能外推全行业'}]}


def install_test_designer(monkeypatch):
    """Emulate the optional plugin at its exchange boundary for manuscript workflow tests."""
    from contextlib import contextmanager
    import hashlib
    from pathlib import Path
    from tempfile import TemporaryDirectory
    from PIL import Image
    from plugins.operations import designer_render

    @contextmanager
    def exchange(spec, source=None):
        with TemporaryDirectory() as tmp:
            folder = Path(tmp)
            phase = spec['phase']
            if phase == 'design':
                title = spec['brief']['title']
                result = {'design': {'template': 'editorial', 'title': title}, 'panel': 'bottom',
                          'reason': '适合稿件', 'background_prompt': '', 'usage': {'total_tokens': 10}}
            elif phase == 'review':
                result = {'review': {'pass': True, 'issues': [], 'reason': '通过'}, 'usage': {'total_tokens': 10}}
            else:
                color = '#' + hashlib.sha256(spec['title'].encode()).hexdigest()[:6]
                Image.new('RGB', (1080, 1440), color).save(folder / ('cover.jpg' if source else 'cover.png'))
                result = {}
            yield folder, result
    monkeypatch.setattr(designer_render, 'check_plugin', lambda: None)
    monkeypatch.setattr(designer_render, 'exchange', exchange)
