"""Content-addressed local cover cache; retries do not redraw or reauthorize revoked art."""
import hashlib
import json

from .cover_design import RENDER_VERSION, TEMPLATES, PALETTES, variations
from .store import encoded


def candidate(store, spec):
    from hermes_platform.fonts import chinese_font, chinese_font_index
    path = chinese_font()
    if path is None:
        raise ValueError('无法生成中文封面，请上传图片或安装中文字体')
    stat = path.stat()
    signature = hashlib.sha256(encoded({'renderer': RENDER_VERSION, 'spec': spec, 'font': str(path),
        'face': chinese_font_index(path), 'size': stat.st_size, 'mtime': stat.st_mtime_ns}).encode()).hexdigest()
    key = 'cover-render:' + signature
    with store.connection() as db:
        saved = db.execute("SELECT data FROM objects WHERE id=? AND kind='cover_render'", (key,)).fetchone()
        record = json.loads(saved[0]) if saved else None
        cached = ({key: record[key] for key in ('asset_id', 'cover', 'template_label', 'palette_label', 'layout')} if record else None)
        asset = db.execute("SELECT data FROM objects WHERE id=? AND kind='asset'", (cached['asset_id'],)).fetchone() if cached else None
    if asset:
        value = json.loads(asset[0])
        if not value.get('authorized') or value.get('revoked'):
            raise ValueError('此封面素材已撤回，请更换样式或配色')
        from .publication_snapshot import asset_bytes
        try:
            asset_bytes({**value, 'id': cached['asset_id']})
            return cached
        except (OSError, ValueError):
            pass  # Rebuild a missing/corrupt locally generated file from its specification.
    from .cover_renderer import render
    raw, layout = render(spec, path)
    identity = hashlib.sha256(raw).hexdigest()
    with store.connection() as db:
        prior = db.execute("SELECT data FROM objects WHERE id=? AND kind='asset'", (identity,)).fetchone()
        if prior and (json.loads(prior[0]).get('revoked') or not json.loads(prior[0]).get('authorized')):
            raise ValueError('此封面素材已撤回，请更换样式或配色')
    identity = store.add_asset(TEMPLATES[spec['template']] + '封面.png', raw, True)
    with store.connection() as db:
        row = db.execute("SELECT data FROM objects WHERE id=? AND kind='asset'", (identity,)).fetchone()
        metadata = {**json.loads(row[0]), 'generated_typography': True, 'cover_title': spec['title'],
                    'cover_spec': spec, 'cover_renderer': RENDER_VERSION, 'cover_layout': layout}
        db.execute('UPDATE objects SET data=? WHERE id=?', (encoded(metadata), identity))
    from .workspace_resources import save_asset
    save_asset(store, identity)
    result = {'asset_id': identity, 'cover': spec, 'template_label': TEMPLATES[spec['template']],
              'palette_label': PALETTES[spec['palette']]['name'], 'layout': layout}
    store.put('cover_render', result, key)
    return result


def candidates(store, spec):
    return [candidate(store, variant) for variant in variations(spec)]


def attach(store, parent, value, set_id=None):
    if not value.get('asset_ids'):
        return value
    first = value['asset_ids'][0]
    with store.connection() as db:
        row = db.execute("SELECT data FROM objects WHERE id=? AND kind='asset'", (first,)).fetchone()
        asset = json.loads(row[0]) if row else {}
        selection = db.execute("SELECT data FROM objects WHERE id=? AND kind='cover_set'", (set_id,)).fetchone() if set_id else None
    choices = value.get('cover_candidates') or parent.get('cover_candidates', [])
    if set_id:
        from .content_release import fingerprint
        saved = json.loads(selection[0]) if selection else {}
        if saved.get('content_id') != parent['id'] or saved.get('content_revision') != fingerprint(parent) or saved.get('version') != store.policy()[0]:
            raise ValueError('封面候选与当前稿件不匹配，请重新预览')
        choices = saved['candidates']
        if first not in {item['asset_id'] for item in choices}:
            raise ValueError('所选图片不属于本次封面候选')
    if asset.get('generated_typography') and asset.get('cover_spec'):
        value.update(cover=asset['cover_spec'], cover_origin='generated_typography', cover_article_title=value['title'])
        value['cover_candidates'] = choices if any(item['asset_id'] == first for item in choices) else [
            {'asset_id': first, 'cover': asset['cover_spec'], 'layout': asset.get('cover_layout', {}),
             'template_label': TEMPLATES[asset['cover_spec']['template']], 'palette_label': PALETTES[asset['cover_spec']['palette']]['name']}]
    return value
