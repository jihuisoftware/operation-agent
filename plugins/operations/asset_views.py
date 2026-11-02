"""Small in-app previews; original authorized assets remain unchanged."""
import base64
from io import BytesIO

from PIL import Image, ImageOps


def thumbnail_data(name, data):
    with Image.open(BytesIO(data)) as original:
        image = ImageOps.exif_transpose(original).convert('RGB')
        image.thumbnail((480, 480))
        buffer = BytesIO()
        image.save(buffer, format='JPEG', quality=80)
    return {'name': name, 'data': base64.b64encode(buffer.getvalue()).decode(), 'mime': 'image/jpeg'}
