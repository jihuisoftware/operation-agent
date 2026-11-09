"""Local, cached design candidates make a text draft a complete image/text manuscript."""


def ensure_cover(store, content):
    if content.get('asset_ids'):
        return content
    from .cover_design import normalized
    from .cover_assets import candidates
    spec = normalized(content.get('cover'), content['title'])
    try:
        choices = candidates(store, spec)
    except ValueError:
        fallback = normalized(None, content['title'])
        if spec == fallback:
            raise
        choices = candidates(store, fallback)
    return {**content, 'asset_ids': [choices[0]['asset_id']], 'cover_origin': 'generated_typography',
            'cover': choices[0]['cover'], 'cover_candidates': choices, 'cover_article_title': content['title']}
