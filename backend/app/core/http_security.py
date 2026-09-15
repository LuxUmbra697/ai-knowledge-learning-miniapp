"""Small ASGI boundaries; never log request bodies, authorization or exception text."""
import asyncio
import traceback
from uuid import uuid4

import structlog
from starlette.datastructures import MutableHeaders
from starlette.responses import JSONResponse

logger = structlog.get_logger()


def safe_error_response(scope, error, log=logger):
    trace_id = scope.get('state', {}).get('trace_id') or uuid4().hex
    log.error('unhandled_exception', method=scope.get('method'), trace_id=trace_id, error_type=type(error).__name__,
              locations=[{'file': frame.filename.rsplit('/', 1)[-1].rsplit('\\', 1)[-1], 'line': frame.lineno,
                          'function': frame.name} for frame in traceback.extract_tb(error.__traceback__)[-8:]])
    return JSONResponse({'code': 5000, 'message': f'服务器内部错误，请稍后重试（记录编号 {trace_id}）', 'data': None},
                        status_code=500, headers={'X-Request-ID': trace_id, 'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff'})


class SafeErrorsMiddleware:
    """Catch before Starlette's outer ServerErrorMiddleware re-raises into Uvicorn logs."""
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            return await self.app(scope, receive, send)
        started, completed = False, False

        async def track(message):
            nonlocal started, completed
            if message['type'] == 'http.response.start':
                started = True
            elif message['type'] == 'http.response.body' and not message.get('more_body', False):
                completed = True
            await send(message)

        try:
            await self.app(scope, receive, track)
        except Exception as error:
            response = safe_error_response(scope, error)
            if not started:
                await response(scope, receive, send)
            elif not completed:
                await send({'type': 'http.response.body', 'body': b'', 'more_body': False})


CSP = ("default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
       "img-src 'self' data: blob: https://*.myqcloud.com "
       "https://ai-knowledge-learn.oss-cn-guangzhou.aliyuncs.com; font-src 'self' data:; "
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
                    headers['Content-Security-Policy'] = CSP if scope['path'] != '/docs' else (
                        "default-src 'none'; script-src 'unsafe-inline' https://cdn.jsdelivr.net; "
                        "style-src 'unsafe-inline' https://cdn.jsdelivr.net; img-src data: https://fastapi.tiangolo.com; "
                        "connect-src 'self'; frame-ancestors 'none'; base-uri 'none'")
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
