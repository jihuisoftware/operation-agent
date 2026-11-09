"""Use the configured image backend without changing chat tools or switching providers on error."""
import json
import hashlib
from contextvars import copy_context
from concurrent.futures import ThreadPoolExecutor, TimeoutError

_POOL = ThreadPoolExecutor(max_workers=2, thread_name_prefix="visual-provider")
from pathlib import Path


def selection():
    from tools.image_generation_tool import _read_configured_image_model, _plugin_provider_name
    from hermes_cli.config import load_config_readonly
    from .store import encoded
    config = load_config_readonly().get('image_gen', {})
    def scrub(value):
        if isinstance(value, dict):
            return {key: scrub(item) for key, item in value.items() if key.lower() not in {'api_key', 'token', 'password', 'secret', 'access_token'}}
        return value
    return {'provider': _plugin_provider_name() or 'default', 'model': _read_configured_image_model() or 'default',
            'configuration': hashlib.sha256(encoded(scrub(config)).encode()).hexdigest()}


def available():
    from tools.image_generation_tool import check_image_generation_requirements
    return check_image_generation_requirements()


def generate(prompt):
    future = _POOL.submit(copy_context().run, _generate, prompt)
    try:
        return future.result(timeout=360)
    except TimeoutError as exc:
        future.cancel()
        raise ValueError('生图等待超过360秒，结果待核对；不会自动重发付费请求') from exc


def _generate(prompt):
    from tools.image_generation_tool import _dispatch_to_plugin_provider, _maybe_route_managed_model, image_generate_tool
    raw = _dispatch_to_plugin_provider(prompt, 'landscape')
    if raw is None:
        raw = _maybe_route_managed_model(prompt, 'landscape')
    if raw is None:
        raw = image_generate_tool(prompt, 'landscape', upscale=False, num_images=1)
    result = json.loads(raw)
    if not result.get('success') or not result.get('image'):
        raise ValueError('生图失败：' + str(result.get('error') or '未取得图片'))
    return result


def image_bytes(result):
    from hermes_constants import get_hermes_home
    from agent.image_gen_provider import save_url_image, save_b64_image
    value = result['image']
    if value.startswith(('https://', 'http://')):
        path = save_url_image(value)
    elif value.startswith('data:image/'):
        header, body = value.split(',', 1)
        extension = {'data:image/png;base64': 'png', 'data:image/jpeg;base64': 'jpg', 'data:image/webp;base64': 'webp'}.get(header)
        if not extension:
            raise ValueError('生图输出格式不受支持')
        path = save_b64_image(body, extension=extension)
    else:
        path = Path(value).expanduser().resolve()
    root = (get_hermes_home() / 'cache' / 'generated').resolve()
    if not path.resolve().is_relative_to(root) or path.stat().st_size > 20 * 1024 * 1024:
        raise ValueError('生图输出不在当前 Profile 缓存内或超过 20 MB')
    from io import BytesIO
    from PIL import Image
    raw = path.read_bytes()
    with Image.open(BytesIO(raw)) as image:
        if image.width * image.height > 40_000_000 or min(image.size) < 512:
            raise ValueError('生图分辨率不足或像素数量超限')
        image.convert('RGB').save(output := BytesIO(), format='PNG')
    return output.getvalue()
