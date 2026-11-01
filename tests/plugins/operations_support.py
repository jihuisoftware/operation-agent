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
