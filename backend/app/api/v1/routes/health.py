"""健康检查路由"""

import asyncio
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from app.core.config import get_settings
from app.core.db import get_mysql_pool

router = APIRouter()


@router.get("/health")
async def health_check():
    return {"status": "ok"}


async def probe_database():
    pool = get_mysql_pool()
    if pool is None:
        raise RuntimeError('Database pool unavailable')
    async with pool.acquire() as connection:
        async with connection.cursor() as cursor:
            await cursor.execute('SELECT 1')
            await cursor.fetchone()


@router.get('/ready')
async def readiness(request: Request):
    try:
        await asyncio.wait_for(probe_database(), timeout=2)
        worker = getattr(request.app.state, 'worker', None)
        if get_settings().worker_enabled and (worker is None or worker.done()):
            raise RuntimeError('Worker unavailable')
    except Exception:
        return JSONResponse({'status': 'not_ready'}, status_code=503)
    return {'status': 'ready'}
