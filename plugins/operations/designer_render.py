"""Profile-local exchange with the optional cover-designer Git package."""
from contextlib import contextmanager
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from PIL import Image

from hermes_platform.fonts import chinese_font, chinese_font_index
from plugins.plugin_storage import plugin_data_dir
from .visual_sets import asset_bytes


def check_plugin():
    from hermes_cli.plugins import discover_plugins, get_plugin_manager
    from tools.registry import registry
    discover_plugins()
    manager = get_plugin_manager()
    selected = any(row['key'] == 'cover-designer' and row['enabled'] and not row['error'] for row in manager.list_plugins())
    if not selected or not registry.snapshot_registration('cover_generate', scope=manager.scope_key):
        raise ValueError('请在当前 Profile 安装并启用封面设计插件')


@contextmanager
def exchange(spec, source=None):
    from tools.registry import registry
    from hermes_cli.plugins import get_plugin_manager
    root = plugin_data_dir('cover-designer') / 'exchange'
    root.mkdir(exist_ok=True)
    with TemporaryDirectory(prefix='cover-', dir=root) as temporary:
        folder = Path(temporary)
        (folder / 'request.json').write_text(json.dumps(spec, ensure_ascii=False), encoding='utf-8')
        if source is not None:
            (folder / 'input').write_bytes(source)
        response = registry.dispatch('cover_generate', {'ticket': folder.name}, scope=get_plugin_manager().scope_key)
        result = json.loads(response)
        if result.get('ticket') != folder.name:
            raise ValueError(result.get('error') or '封面设计插件未返回本次任务结果')
        yield folder, result


def background_prompt(spec):
    with exchange({**spec, 'phase': 'background'}) as (_, result):
        prompt = result.get('prompt')
        if not isinstance(prompt, str) or not 0 < len(prompt.strip()) <= 4000:
            raise ValueError('封面插件未提供有效的底图描述')
        return prompt


def generate_background(store, prompt):
    from . import visual_provider
    raw = visual_provider.image_bytes(visual_provider.generate(prompt, aspect_ratio='portrait'))
    identity = store.add_asset('AI封面底图.png', raw, True, cover_metadata={'designer_background': True})
    if not identity:
        raise ValueError('生成底图已撤销使用授权')
    return identity


def render(store, job):
    raw = asset_bytes(store, job['background'])
    if job['mode'] == 'upload':
        return job['background']
    font = chinese_font()
    if font is None:
        raise ValueError('请安装中文字体后重新生成封面')
    spec = {**job['spec'], 'phase': 'compose', 'font_path': str(font), 'font_face': chinese_font_index(font)}
    with exchange(spec, raw) as (folder, _):
        output = folder / 'cover.jpg'
        if output.is_symlink() or output.stat().st_size > 20 * 1024 * 1024:
            raise ValueError('封面文件无效')
        with Image.open(output) as rendered:
            if rendered.size != (1080, 1440) or rendered.format != 'JPEG':
                raise ValueError('候选封面尺寸或格式错误')
        metadata = {'designer_cover': True, 'cover_spec': {k: spec[k] for k in ('title', 'subtitle')}}
        identity = store.add_asset('设计封面.jpg', output.read_bytes(), True, cover_metadata=metadata)
        if not identity:
            raise ValueError('此候选封面已撤销使用授权')
        return identity
