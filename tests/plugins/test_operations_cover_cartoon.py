"""Cartoon artwork stays inside the chosen cover family throughout preview and reuse."""
from plugins.operations.cover_assets import candidates
from plugins.operations.cover_cartoon_catalog import CHARACTERS, GROUPS
from plugins.operations.cover_design import normalized
from plugins.operations.store import Store


def test_cartoon_candidates_keep_selected_character_and_palette(tmp_path, monkeypatch):
    monkeypatch.setenv('HERMES_HOME', str(tmp_path))
    store = Store()
    spec = normalized({'template': 'cartoon', 'variant': 'bear-girl', 'title': '荷兰猪第一周',
                       'keywords': ['新手必看'], 'subtitle': '从布置小窝开始'}, '', strict=True)
    choices = candidates(store, spec)
    assert choices[0]['cover'] == spec
    assert {choice['cover']['template'] for choice in choices} == {'cartoon'}
    assert {choice['palette_label'] for choice in choices} == {'草莓粉'}
    assert len({choice['asset_id'] for choice in choices}) == 3
    for choice in choices:
        assert choice['cover']['variant'] in GROUPS['日系小人']
        assert choice['variant_label'] == CHARACTERS[choice['cover']['variant']]
        assert ''.join(choice['layout']['title']['lines']) == spec['title']
    assert candidates(store, spec) == choices


def test_default_column_label_is_absent_and_the_same_words_can_be_a_title():
    for fields in ({}, {'eyebrow': '主题分享'}):
        spec = normalized({'template': 'cartoon', **fields}, '我的主题分享')
        assert spec['eyebrow'] == ''
        assert spec['title'] == '我的主题分享'
    assert normalized({'eyebrow': '饲养日记'}, '荷兰猪')['eyebrow'] == '饲养日记'
