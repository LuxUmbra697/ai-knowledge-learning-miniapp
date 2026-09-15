"""Private illustration objects only; no bucket-wide policy changes or enumeration."""
import asyncio
import re
from functools import lru_cache
from urllib.parse import urlsplit, urlunsplit

import httpx
from qcloud_cos import CosConfig, CosS3Client

from app.core.config import get_settings


def object_key(asset_id):
    if not re.fullmatch(r'asset_[a-f0-9]{32}', asset_id):
        raise ValueError('Invalid asset identity')
    prefix = get_settings().cos_upload_prefix.strip('/')
    if any(part in ('.', '..') for part in prefix.split('/')) or '\\' in prefix or any(ord(char) < 32 for char in prefix):
        raise ValueError('Invalid private object prefix')
    return '/'.join(filter(None, (prefix, 'ai-learn-private-v1', asset_id + '.jpg')))


def validate_key(key):
    name = key.rsplit('/', 1)[-1]
    if not name.endswith('.jpg') or object_key(name[:-4]) != key:
        raise ValueError('Object is outside the current illustration namespace')
    return key


@lru_cache
def client():
    settings = get_settings()
    config = CosConfig(Region=settings.cos_region, SecretId=settings.cos_secret_id, SecretKey=settings.cos_secret_key,
                       Scheme='https', Timeout=10, PoolConnections=2, PoolMaxSize=2, AllowRedirects=False, VerifySSL=True)
    return CosS3Client(config, retry=0)


def signed_url(key):
    validate_key(key)
    return client().get_presigned_url(Bucket=get_settings().cos_bucket, Key=key, Method='GET', Expired=120)


async def anonymous_denied(key):
    parts = urlsplit(signed_url(key))
    url = urlunsplit((parts.scheme, parts.netloc, parts.path, '', ''))
    async with (httpx.AsyncClient(timeout=8, trust_env=False, follow_redirects=False) as http,
                http.stream('GET', url) as response):
        if response.status_code != 403:
            raise ValueError('Private storage did not deny anonymous reading')


def _put(key, data, content_type):
    validate_key(key)
    client().put_object(Bucket=get_settings().cos_bucket, Key=key, Body=data, ContentType=content_type,
                        ACL='private', CacheControl='private, no-store', EnableMD5=True)


async def verify_storage(key):
    # The non-sensitive probe uses this task's reserved final key, so crash cleanup can find it.
    await asyncio.to_thread(_put, key, b'AI Learning Studio private access probe', 'application/octet-stream')
    await anonymous_denied(key)


async def upload(key, data):
    await asyncio.to_thread(_put, key, data, 'image/jpeg')
    await anonymous_denied(key)


async def delete(key):
    validate_key(key)
    await asyncio.to_thread(client().delete_object, Bucket=get_settings().cos_bucket, Key=key)
