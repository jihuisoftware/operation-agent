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
