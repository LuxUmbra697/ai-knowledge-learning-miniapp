"""A single bounded public search, never a URL extractor or a private-corpus tool."""
import asyncio
import ipaddress
import json
from urllib.parse import urlsplit

import httpx
from fastapi import HTTPException

from app.core.config import get_settings

ENDPOINT = 'https://api.tavily.com/search'
MAX_RESPONSE_BYTES = 65536


def require_available():
    settings = get_settings()
    if not settings.enable_web_search or not settings.tavily_api_key:
        raise HTTPException(422, '网页参考暂未开启，可以关闭网页参考后生成普通主题练习')
    return settings


def safe_source_url(value):
    if not isinstance(value, str) or len(value) > 1500:
        return None
    try:
        parsed = urlsplit(value)
        if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password or parsed.port not in (None, 443):
            return None
        host = parsed.hostname.lower().rstrip('.')
        if '.' not in host or host.endswith(('.local', '.internal', '.localhost', '.test', '.invalid')):
            return None
        try:
            if not ipaddress.ip_address(host).is_global:
                return None
        except ValueError:
            pass
        return value
    except ValueError:
        return None


def normalize_results(data):
    if not isinstance(data, dict) or not isinstance(data.get('results'), list):
        raise HTTPException(502, '网页参考返回格式不完整，未生成练习')
    items, seen = [], set()
    for row in data['results'][:3]:
        if not isinstance(row, dict):
            continue
        url = safe_source_url(row.get('url'))
        content, title = row.get('content'), row.get('title')
        if not url or url in seen or not isinstance(content, str) or not content.strip() or not isinstance(title, str):
            continue
        seen.add(url)
        items.append({'title': title[:160], 'url': url, 'excerpt': content.strip()[:1000]})
    return {'source_type': 'public_web', 'status': 'found' if items else 'no_results', 'sources': items,
                'verification': 'reference_only_not_question_level_verified'}


async def _search(query, settings):
    async with (
        httpx.AsyncClient(timeout=15, follow_redirects=False, trust_env=False) as client,
        client.stream('POST', ENDPOINT, headers={'Authorization': f'Bearer {settings.tavily_api_key}'},
                      json={'query': query, 'search_depth': 'basic', 'max_results': 3,
                            'include_raw_content': False, 'include_answer': False, 'include_images': False,
                            'auto_parameters': False}) as response,
    ):
        if response.status_code in (401, 403):
            raise HTTPException(503, '网页参考服务授权失败，未继续调用')
        if response.status_code in (429, 432, 433):
            raise HTTPException(429, '网页参考服务额度或频率受限，请稍后再试')
        if response.status_code != 200:
            raise HTTPException(502, '网页参考服务暂不可用，未生成练习')
        body = bytearray()
        async for part in response.aiter_bytes():
            body.extend(part)
            if len(body) > MAX_RESPONSE_BYTES:
                raise HTTPException(502, '网页参考内容超过处理限制')
    try:
        return normalize_results(json.loads(body)), None
    except (ValueError, UnicodeDecodeError) as error:
        raise HTTPException(502, '网页参考返回格式无效，未生成练习') from error


async def fetch_context(context):
    if context.payload.get('doc_ids') or context.payload.get('scope'):
        raise HTTPException(422, '私人材料不能进入网页搜索')
    saved = context.checkpoints.get('public_search', {}).get('output')
    if saved is None:
        settings = require_available()

        async def operation():
            try:
                return await asyncio.wait_for(_search(context.payload['query'], settings), timeout=18)
            except (TimeoutError, httpx.TimeoutException) as error:
                raise HTTPException(504, '网页参考请求超时，未自动重复调用') from error
            except httpx.HTTPError as error:
                raise HTTPException(502, '网页参考网络暂不可用，未自动重复调用') from error

        saved = await context.external('public_search', operation, len(context.payload['query'].encode()))
    if saved['status'] != 'found':
        raise HTTPException(422, '未找到可用网页参考，可以修改主题或关闭网页参考后重新生成')
    return json.dumps(saved, ensure_ascii=False)
