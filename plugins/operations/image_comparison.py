"""Local visual references only: similarity never upgrades exact publication verification."""
from io import BytesIO
from PIL import Image, ImageChops, ImageOps, ImageStat
from .publication_snapshot import asset_bytes


def decode(raw):
    with Image.open(BytesIO(raw)) as image:
        if image.width * image.height > 16_000_000 or image.format not in {'PNG', 'JPEG', 'WEBP'}:
            raise ValueError('图片格式或像素数量超过核对上限')
        return ImageOps.exif_transpose(image).convert('RGBA')


def compare(original, remote):
    left, right = decode(original), decode(remote)
    exact = left.size == right.size and left.tobytes() == right.tobytes()
    a, b = left.convert('RGB').resize((64, 64)), right.convert('RGB').resize((64, 64))
    difference = sum(ImageStat.Stat(ImageChops.difference(a, b)).mean) / (3 * 255)
    return {'original_size': list(left.size), 'platform_size': list(right.size), 'pixels_equal': exact,
            'similarity': round(max(0, 1 - difference), 4), 'reference_only': True}


def reference(asset, raw):
    try:
        return compare(asset_bytes(asset), raw)
    except (OSError, ValueError, Image.DecompressionBombError) as exc:
        return {'reference_only': True, 'error': type(exc).__name__}


def thumbnail(raw):
    import base64
    image = decode(raw)
    image.thumbnail((640, 640))
    buffer = BytesIO()
    image.convert('RGB').save(buffer, format='JPEG', quality=80)
    return 'data:image/jpeg;base64,' + base64.b64encode(buffer.getvalue()).decode()
