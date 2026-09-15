"""Budgeted illustrations run after the text quiz is committed, using a private object namespace."""
import asyncio
import hashlib
import io
import json
import re
from urllib.parse import urlsplit

import httpx
import structlog
from fastapi import HTTPException
from PIL import Image
from qcloud_cos.cos_exception import CosClientError, CosServiceError

from app.core.config import get_settings
from app.repositories import job_repository as jobs
from app.repositories import quiz_image_repository as assets
from app.repositories import quiz_repository
from app.services import private_cos_service as storage
from app.services.image_service import _derive_image_base_url
from app.services.outbound_service import fetch_public, validate_url

logger = structlog.get_logger()
NEGATIVE_PROMPT = 'Text, letters, words, numbers, labels, question paper, poster, captions, speech bubbles, screenshots, interface, watermark, instructions printed in the picture.'


def image_prompt(question):
    return ('A single hand-painted educational illustration, soft natural light, clear visual shapes, restrained green and coral accents. '
            'Depict the actual objects and their relationship, using pictures only. '
            f"The visual subject is {question['knowledge_point'][:100]}. "
            f"Scene context: {question['stem'][:500]}. "
            'Full-bleed square composition, generous empty space, absolutely no text, page, poster, labels or written instructions.')


def image_endpoint(embedding_base, image_base):
    base = image_base or _derive_image_base_url(embedding_base)
    parts = urlsplit(base)
    if (parts.scheme != 'https' or not parts.hostname or parts.username or parts.password or parts.query or parts.fragment
            or parts.port not in (None, 443) or not parts.path.rstrip('/').endswith('/api/v1')):
        raise ValueError('Image provider requires a native HTTPS API endpoint')
    return base.rstrip('/') + '/services/aigc/multimodal-generation/generation'


def require_config():
    settings = get_settings()
    if not settings.dashscope_image_api_key:
        raise HTTPException(422, '配图模型暂未配置，可以关闭配图后生成文字练习')
    if not all((settings.cos_secret_id, settings.cos_secret_key, settings.cos_region, settings.cos_bucket)):
        raise HTTPException(422, '配图私有存储暂未配置，可以关闭配图后继续')
    try:
        image_endpoint(settings.dashscope_base_url, settings.dashscope_image_base_url)
    except ValueError as error:
        raise HTTPException(422, '配图接口配置无效，可以关闭配图后继续') from error
    if not re.fullmatch(r'\d{3,4}\*\d{3,4}', settings.image_gen_size):
        raise HTTPException(422, '配图尺寸配置无效')
    width, height = map(int, settings.image_gen_size.split('*'))
    if not 512 * 512 <= width * height <= 2048 * 2048 or max(width, height) > 4096:
        raise HTTPException(422, '配图尺寸超出处理预算')
    return settings


async def generate(prompt):
    settings = require_config()
    endpoint = image_endpoint(settings.dashscope_base_url, settings.dashscope_image_base_url)
    async with (
        httpx.AsyncClient(timeout=35, trust_env=False, follow_redirects=False) as client,
        client.stream('POST', endpoint, headers={'Authorization': 'Bearer ' + settings.dashscope_image_api_key},
                      json={'model': settings.dashscope_image_model, 'input': {'messages': [{'role': 'user', 'content': [{'text': prompt}]}]},
                            'parameters': {'n': 1, 'size': settings.image_gen_size, 'prompt_extend': False, 'watermark': False, 'negative_prompt': NEGATIVE_PROMPT}}) as response,
    ):
        if response.status_code in (401, 403):
            raise HTTPException(503, '配图模型授权失败，未重复调用')
        if response.status_code == 429:
            raise HTTPException(429, '配图模型额度或频率受限，未重复调用')
        if response.status_code != 200:
            raise HTTPException(502, '配图模型暂不可用，文字练习不受影响')
        body = bytearray()
        async for block in response.aiter_bytes():
            if len(body) + len(block) > 65536:
                raise ValueError('Image provider response too large')
            body.extend(block)
    data = json.loads(body)
    choices = data['output']['choices']
    if len(choices) != 1 or choices[0].get('finish_reason', 'stop') != 'stop':
        raise ValueError('Incomplete image provider response')
    content = choices[0]['message']['content']
    urls = [part['image'] for part in content if isinstance(part, dict) and 'image' in part]
    if len(urls) != 1:
        raise ValueError('Expected exactly one image')
    validate_url(urls[0])
    return {'url': urls[0], 'image_count': 1}, None


def compress(data):
    if len(data) > 8 * 1024 * 1024:
        raise ValueError('Image file too large')
    with Image.open(io.BytesIO(data), formats=['PNG', 'JPEG']) as image:
        width, height = image.size
        if min(width, height) < 32 or max(width, height) > 4096 or width * height > 2048 * 2048:
            raise ValueError('Image dimensions exceed memory budget')
        if getattr(image, 'n_frames', 1) != 1:
            raise ValueError('Animated images are not supported')
        image.load()
        image = image.convert('RGB')
        image.thumbnail((640, 640))
        target = io.BytesIO()
        image.save(target, format='JPEG', quality=82, optimize=True)
        result = target.getvalue()
        if len(result) > 350000:
            raise ValueError('Compressed image exceeds delivery budget')
        return result, {'width': image.width, 'height': image.height, 'size_bytes': len(result), 'sha256': hashlib.sha256(result).hexdigest()}


async def persist_image(asset, output):
    downloaded = await fetch_public(output['url'], max_bytes=8 * 1024 * 1024, content_types={'image/png', 'image/jpeg'}, timeout=10)
    data, metadata = await asyncio.to_thread(compress, downloaded.content)
    await storage.upload(asset['object_key'], data)
    return {'asset_id': asset['asset_id'], 'state': 'ready', **metadata}


async def run(context):
    rows = await assets.for_task(context)
    if context.payload['doc_ids']:
        from app.services.job_handlers import validate_scope
        await validate_scope(context)
    quiz = await quiz_repository.get_quiz_detail(context.payload['quiz_id'], context.user_id)
    if not quiz:
        raise HTTPException(404, '练习不存在')
    questions = {row['id']: row for row in quiz['questions']}
    outcomes = []
    permanent_error = None
    for number, row in enumerate(rows, 1):
        saved = context.checkpoints.get('image_saved_' + str(number))
        if saved:
            outcomes.append(saved)
            continue
        try:
            if permanent_error:
                raise HTTPException(503, '配图服务不可用，未继续调用')
            if context.payload['doc_ids']:
                from app.services.job_handlers import validate_scope
                await validate_scope(context)
            row = await assets.reserve(context, row['asset_id'])
            stage = 'image_' + str(number)
            output = context.checkpoints.get(stage, {}).get('output')
            if output is None:
                require_config()
                await storage.verify_storage(row['object_key'])
                question = questions[row['question_id']]
                prompt = image_prompt(question)

                async def operation(value=prompt):
                    return await asyncio.wait_for(generate(value), timeout=40)

                output = await context.external(stage, operation, len(prompt.encode()))
            result = await persist_image(row, output)
        except (jobs.TaskLeaseLost, jobs.TaskBudgetExceeded):
            raise
        except (HTTPException, ValueError, KeyError, TypeError, OSError, httpx.HTTPError, CosClientError, CosServiceError) as error:
            if isinstance(error, HTTPException) and error.status_code in (422, 429, 503):
                permanent_error = error.status_code
            code = f'http_{error.status_code}' if isinstance(error, HTTPException) else type(error).__name__
            result = {'asset_id': row['asset_id'], 'state': 'failed', 'error_code': code}
        await context.checkpoint('image_saved_' + str(number), result)
        outcomes.append(result)
    if context.payload['doc_ids']:
        from app.services.job_handlers import validate_scope
        await validate_scope(context)
    return await assets.finish(context, outcomes)


async def get_image(asset_id, user_id):
    row = await assets.get_owned(asset_id, user_id)
    state = row['state']
    if row['job_status'] in ('failed', 'cancelled') or state == 'removed':
        state = 'failed'
    elif state == 'ready' and row['job_status'] != 'completed':
        state = 'reserved'
    elif state == 'ready' and not row.get('answered'):
        state = 'locked'
    data = {'asset_id': asset_id, 'task_id': row['task_id'], 'status': state, 'stage': row['job_stage'], 'url': None,
            'message': '配图未完成，文字练习不受影响' if state == 'failed' else None}
    if state == 'locked':
        data['message'] = '配图已完成，作答后可查看'
    if state == 'ready' and row['job_status'] == 'completed':
        data.update(url=storage.signed_url(row['object_key']), expires_in=120)
    return data


async def maintenance():
    for row in await assets.cleanup_candidates():
        try:
            await storage.delete(row['object_key'])
            await assets.removed(row['asset_id'])
        except (ValueError, OSError, httpx.HTTPError, CosClientError, CosServiceError) as error:
            await assets.cleanup_failed(row['asset_id'])
            logger.warning('image_cleanup_pending', asset_id=row['asset_id'], error_type=type(error).__name__)
