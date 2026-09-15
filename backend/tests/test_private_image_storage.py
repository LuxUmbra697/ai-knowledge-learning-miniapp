import io
from unittest.mock import Mock

import pytest
from app.services import private_cos_service as storage
from app.services import quiz_image_service as images
from PIL import Image


def test_private_object_operations_are_scoped_and_never_inherit_public_acl(monkeypatch):
    settings = storage.get_settings().model_copy(update={'cos_upload_prefix': 'isolated-smoke/', 'cos_bucket': 'synthetic-bucket'})
    monkeypatch.setattr(storage, 'get_settings', lambda: settings)
    client = Mock(); monkeypatch.setattr(storage, 'client', lambda: client)
    key = storage.object_key('asset_' + 'a' * 32)
    storage._put(key, b'fixture', 'image/jpeg')
    assert client.put_object.call_args.kwargs['ACL'] == 'private'
    assert client.put_object.call_args.kwargs['CacheControl'] == 'private, no-store'
    storage.signed_url(key)
    assert client.get_presigned_url.call_args.kwargs['Expired'] == 120
    for invalid in ('../other.jpg', 'other-project/' + key.rsplit('/', 1)[-1], key.replace('ai-learn-private-v1', 'uploads'), key + '?signature=x'):
        with pytest.raises(ValueError):
            storage.validate_key(invalid)


def test_downloaded_images_have_bounded_dimensions_and_no_inherited_metadata():
    output = io.BytesIO()
    Image.new('RGB', (1024, 512), '#39826f').save(output, format='PNG')
    data, meta = images.compress(output.getvalue())
    assert (meta['width'], meta['height']) == (640, 320)
    assert meta['size_bytes'] == len(data) < 350000
    with Image.open(io.BytesIO(data)) as image:
        assert image.format == 'JPEG' and not image.getexif()
    for bad in (b'<svg onload="alert(1)"/>', output.getvalue()[:30], b'x' * (8 * 1024 * 1024 + 1)):
        with pytest.raises((ValueError, OSError)):
            images.compress(bad)
