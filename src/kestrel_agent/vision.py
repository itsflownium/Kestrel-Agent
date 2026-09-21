"""Bounded image inputs; pixels stay outside textual observations and logs."""
from dataclasses import dataclass, field
from collections import OrderedDict
import base64
import hashlib
import io
import time
import warnings

MAX_BYTES = 4 * 1024 * 1024
MAX_PIXELS = 16_000_000


@dataclass(frozen=True)
class ImageEvidence:
    data: bytes = field(repr=False)
    mime: str
    width: int
    height: int
    sha256: str
    observed_at: float

    @property
    def encoded(self):
        return base64.b64encode(self.data).decode('ascii')

    @property
    def url(self):
        return f'data:{self.mime};base64,{self.encoded}'

    def metadata(self):
        return {'mime': self.mime, 'width': self.width, 'height': self.height,
                'sha256': self.sha256, 'observed_at': self.observed_at}


def validate_image(data, claimed_mime=None):
    from PIL import Image
    if not data or len(data) > MAX_BYTES:
        raise ValueError('Images must contain 1 byte to 4 MiB.')
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(data)) as image:
                mime = {'PNG':'image/png', 'JPEG':'image/jpeg', 'WEBP':'image/webp'}.get(image.format)
                if not mime or (claimed_mime and claimed_mime != mime):
                    raise ValueError('Use PNG, JPEG, or WebP with a matching media type.')
                width, height = image.size
                if width * height > MAX_PIXELS or getattr(image, 'n_frames', 1) != 1:
                    raise ValueError('Use a single-frame image no larger than 16 megapixels.')
                image.verify()
    except (OSError, Image.DecompressionBombError, Image.DecompressionBombWarning) as error:
        raise ValueError('Invalid or oversized image.') from error
    return ImageEvidence(bytes(data), mime, width, height, hashlib.sha256(data).hexdigest(), time.time())


class ImageCache:
    """Eight recent connector images; missing/evicted IDs require a new observation."""
    def __init__(self):
        self.entries = OrderedDict()

    def ingest(self, result):
        for block in result.get('content', []):
            if block.get('type') == 'image':
                encoded = block.pop('data', '')
                try:
                    if not isinstance(encoded, str) or len(encoded) > (MAX_BYTES * 4 // 3 + 8):
                        raise ValueError('Encoded image exceeds the input limit.')
                    image = validate_image(base64.b64decode(encoded, validate=True), block.get('mimeType'))
                    key = 'image:' + image.sha256
                    self.entries[key] = image
                    self.entries.move_to_end(key)
                    while len(self.entries) > 8:
                        self.entries.popitem(last=False)
                    block.update(image_id=key, **image.metadata(), instruction='Use inspect_image with this image_id as source to view pixels. Metadata alone is not visual evidence.')
                except (ValueError, TypeError):
                    block['unavailable_to_model'] = 'Invalid or unsupported image. Request a new PNG/JPEG/WebP observation.'
            elif block.get('type') == 'audio':
                block.pop('data', None)
                block['unavailable_to_model'] = 'Audio inspection is unavailable; request text.'
        return result

    def get(self, key):
        if key not in self.entries:
            raise ValueError('Image expired or belongs to another runtime. Capture a new observation.')
        return self.entries[key]
