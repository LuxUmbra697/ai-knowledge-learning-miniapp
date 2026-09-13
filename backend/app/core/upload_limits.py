"""Bound multipart buffering before the framework parses or spools uploads."""
import asyncio
from starlette.responses import JSONResponse
from app.core.config import get_settings


class UploadLimitsMiddleware:
    def __init__(self, app):
        self.app = app
        self.slots = asyncio.Semaphore(2)

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http' or scope['method'] != 'POST' or scope['path'].rstrip('/') != '/api/v1/knowledge/documents':
            return await self.app(scope, receive, send)
        limit = get_settings().kb_max_file_size_mb * 1024 * 1024 + 65536

        async def reject(code, message):
            await JSONResponse(status_code=code, content={'code': code, 'message': message, 'data': None})(scope, receive, send)

        length = dict(scope['headers']).get(b'content-length')
        if length is not None:
            try:
                if int(length) < 0:
                    raise ValueError
                if int(length) > limit:
                    return await reject(413, '上传文件超过大小限制')
            except ValueError:
                return await reject(400, '上传请求长度无效')
        try:
            await asyncio.wait_for(self.slots.acquire(), timeout=2)
        except asyncio.TimeoutError:
            return await reject(429, '当前上传较多，请稍后重试')
        try:
            chunks, size = [], 0
            async with asyncio.timeout(30):
                while True:
                    message = await receive()
                    if message['type'] == 'http.disconnect':
                        return
                    chunk = message.get('body', b'')
                    size += len(chunk)
                    if size > limit:
                        return await reject(413, '上传文件超过大小限制')
                    chunks.append(chunk)
                    if not message.get('more_body', False):
                        break
            body = b''.join(chunks)
            chunks.clear()
            delivered = False

            async def replay():
                nonlocal delivered
                if delivered:
                    return await receive()
                delivered = True
                return {'type': 'http.request', 'body': body, 'more_body': False}

            await self.app(scope, replay, send)
        except asyncio.TimeoutError:
            await reject(408, '文件上传超时，请检查网络后重试')
        finally:
            self.slots.release()
