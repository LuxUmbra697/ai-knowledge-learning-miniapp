"""Small ASGI boundaries; never log request bodies, authorization or exception text."""
import asyncio
from uuid import uuid4

from starlette.datastructures import MutableHeaders
from starlette.responses import JSONResponse


CSP = ("default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
       "img-src 'self' data: blob: https://*.myqcloud.com; font-src 'self' data:; "
       "connect-src 'self' blob:; object-src 'none'; base-uri 'self'; frame-ancestors 'none'; form-action 'self'")


class SecurityHeadersMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            return await self.app(scope, receive, send)
        trace_id = uuid4().hex
        scope.setdefault('state', {})['trace_id'] = trace_id

        async def secure_send(message):
            if message['type'] == 'http.response.start':
                headers = MutableHeaders(scope=message)
                headers['X-Request-ID'] = trace_id
                headers['X-Content-Type-Options'] = 'nosniff'
                headers['X-Frame-Options'] = 'DENY'
                headers['Referrer-Policy'] = 'no-referrer'
                headers['Permissions-Policy'] = 'camera=(), microphone=(), geolocation=()'
                if scope['path'].startswith('/api'):
                    headers['Cache-Control'] = 'no-store'
                if 'text/html' in headers.get('content-type', ''):
                    headers['Content-Security-Policy'] = CSP
                    headers['Cache-Control'] = 'no-cache'
            await send(message)

        await self.app(scope, receive, secure_send)


class JsonBodyLimitsMiddleware:
    def __init__(self, app):
        self.app = app
        self.slots = asyncio.Semaphore(8)

    async def __call__(self, scope, receive, send):
        if (scope['type'] != 'http' or scope['method'] not in ('POST', 'PUT', 'PATCH', 'DELETE')
                or not scope['path'].startswith('/api/')
                or scope['path'].rstrip('/') == '/api/v1/knowledge/documents'):
            return await self.app(scope, receive, send)
        limit = 512 * 1024

        async def reject(code):
            messages = {400: '请求长度无效', 408: '请求接收超时，请重试', 413: '请求内容过大', 429: '请求较多，请稍后重试'}
            await JSONResponse({'code': code, 'message': messages[code], 'data': None}, status_code=code)(scope, receive, send)

        length = dict(scope['headers']).get(b'content-length')
        if length is not None:
            try:
                if int(length) < 0:
                    raise ValueError
                if int(length) > limit:
                    return await reject(413)
            except ValueError:
                return await reject(400)
        try:
            await asyncio.wait_for(self.slots.acquire(), timeout=2)
        except TimeoutError:
            return await reject(429)
        try:
            chunks, size = [], 0
            try:
                async with asyncio.timeout(10):
                    while True:
                        message = await receive()
                        if message['type'] == 'http.disconnect':
                            return
                        chunk = message.get('body', b'')
                        size += len(chunk)
                        if size > limit:
                            return await reject(413)
                        chunks.append(chunk)
                        if not message.get('more_body', False):
                            break
            except TimeoutError:
                return await reject(408)
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
        finally:
            self.slots.release()
