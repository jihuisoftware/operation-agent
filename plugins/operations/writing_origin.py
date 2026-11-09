"""Origins are server-owned: deriving from an AI manuscript cannot erase its evidence."""
import json

from .writing_document import from_plain, SCHEMA_VERSION


def original(content):
    value = content.get('authorship', {})
    return value.get('kind') == 'human_original' and value.get('declared') is True


def initial(db, body):
    from .writing_drafts import read, fields
    if body.get('copy_from'):
        source = read(db, body['copy_from'])
        value = fields(body['local']) if body.get('local') else fields(source)
        if source['origin']['kind'] == 'derived' and value['original']:
            raise ValueError('派生稿件不能移除原稿依据')
        return {**value, 'origin': source['origin'], 'copied_from': source['id']}
    if body.get('from_content'):
        from .content_release import fingerprint
        row = db.execute("SELECT data FROM objects WHERE kind='content' AND id=?", (body['from_content'],)).fetchone()
        if not row:
            raise ValueError('原稿不存在于当前主题')
        content = json.loads(row[0])
        return {'title': content['title'], 'document': content.get('editor_document') or from_plain(content['body'], content.get('asset_ids', [])),
                'document_version': SCHEMA_VERSION, 'cover_asset_id': (content.get('asset_ids') or [''])[0],
                'source_ids': content.get('source_ids', []), 'original': original(content),
                'origin': {'kind': 'original' if original(content) else 'derived', 'content_id': body['from_content'], 'content_revision': fingerprint(content)}}
    return {'title': '', 'document': from_plain(''), 'document_version': SCHEMA_VERSION, 'cover_asset_id': '',
            'source_ids': [], 'original': False, 'origin': {'kind': 'original'}}
