"""题目配图生成记录数据访问层（用于每日生图次数限制）"""

from __future__ import annotations

from typing import Optional

import structlog
from fastapi import HTTPException

from app.core.db import get_mysql_pool

logger = structlog.get_logger()


async def get_today_usage_count(user_id: int) -> int:
    """Get successful images in the current UTC database session day; missing storage fails closed."""
    pool = get_mysql_pool()
    if pool is None:
        raise HTTPException(503, '配图额度暂时不可用')
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "SELECT COUNT(*) FROM image_generation_logs "
                "WHERE user_id = %s AND created_at >= CURDATE()",
                (user_id,),
            )
            row = await cur.fetchone()
            return row[0] if row else 0


async def log_image_generation(
    user_id: int,
    quiz_id: Optional[str],
    question_id: Optional[str],
    image_url: str,
) -> None:
    """记录一次成功的生图，用于每日次数统计。"""
    pool = get_mysql_pool()
    if pool is None:
        raise HTTPException(503, '配图记录暂时不可用')
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "INSERT INTO image_generation_logs (user_id, quiz_id, question_id, image_url) "
                "VALUES (%s, %s, %s, %s)",
                (user_id, quiz_id, question_id, image_url),
            )
