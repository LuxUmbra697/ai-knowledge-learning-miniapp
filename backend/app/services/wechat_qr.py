"""Official mini-program scene codes; no website OAuth AppID substitution."""
import asyncio
import base64
import time

import httpx
from fastapi import HTTPException

from app.core.config import get_settings

_token = None
_lock = asyncio.Lock()


def provider_error(code):
    messages = {40164: '微信服务端 IP 白名单尚未配置，请联系管理员',
                40013: '微信应用配置无效，请联系管理员', 40125: '微信应用凭据需要更新，请联系管理员',
                41030: '微信扫码入口尚未发布，请管理员发布对应小程序版本',
                48001: '当前微信账号尚未开通小程序码权限', 45009: '微信扫码服务额度已达上限，请稍后重试'}
    return HTTPException(503, messages.get(code, '微信扫码服务暂不可用，请使用账号密码登录'))


async def access_token():
    global _token
    settings = get_settings()
    if not settings.wechat_app_id or not settings.wechat_app_secret:
        raise HTTPException(503, '微信扫码服务尚未配置')
    async with _lock:
        if _token and _token[0] == settings.wechat_app_id and _token[2] > time.monotonic():
            return _token[1]
        async with httpx.AsyncClient(timeout=10, follow_redirects=False) as client:
            response = await client.post('https://api.weixin.qq.com/cgi-bin/stable_token', json={
                'grant_type': 'client_credential', 'appid': settings.wechat_app_id,
                'secret': settings.wechat_app_secret, 'force_refresh': False})
            response.raise_for_status()
            data = response.json()
        if not isinstance(data, dict) or not isinstance(data.get('access_token'), str):
            raise provider_error(data.get('errcode') if isinstance(data, dict) else None)
        _token = (settings.wechat_app_id, data['access_token'], time.monotonic() + min(int(data.get('expires_in', 7200)), 7200) - 120)
        return _token[1]


async def qr_image(scene):
    try:
        token = await access_token()
        async with httpx.AsyncClient(timeout=12, follow_redirects=False) as client:
            async with client.stream('POST', 'https://api.weixin.qq.com/wxa/getwxacodeunlimit', params={'access_token': token}, json={
                'scene': scene, 'page': 'pages/login/index', 'width': 280,
                'check_path': get_settings().wechat_qr_env == 'release', 'env_version': get_settings().wechat_qr_env}) as response:
                response.raise_for_status()
                chunks, size = [], 0
                async for chunk in response.aiter_bytes():
                    size += len(chunk)
                    if size > 1024 * 1024:
                        raise HTTPException(503, '微信二维码响应过大')
                    chunks.append(chunk)
                data = b''.join(chunks)
                if data.startswith(b'\x89PNG\r\n\x1a\n'):
                    mime = 'image/png'
                elif data.startswith(b'\xff\xd8\xff'):
                    mime = 'image/jpeg'
                else:
                    import json
                    result = json.loads(data)
                    raise provider_error(result.get('errcode') if isinstance(result, dict) else None)
                return 'data:' + mime + ';base64,' + base64.b64encode(data).decode('ascii')
    except (httpx.HTTPError, ValueError, TypeError):
        raise HTTPException(503, '微信扫码服务连接失败，请稍后重试或使用账号密码') from None
