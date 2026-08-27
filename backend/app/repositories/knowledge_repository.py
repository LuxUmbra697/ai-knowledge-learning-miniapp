"""知识库文档数据访问层"""

from __future__ import annotations

from typing import Optional

import structlog

from app.core.db import get_mysql_pool

logger = structlog.get_logger()


async def create_document(
    doc_id: str,
    user_id: int,
    file_name: str,
    file_type: str,
    file_size: int,
) -> None:
    pool = get_mysql_pool()
    if pool is None:
        return
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "INSERT INTO kb_documents (doc_id, user_id, file_name, file_type, file_size, status) "
                "VALUES (%s, %s, %s, %s, %s, 'processing')",
                (doc_id, user_id, file_name, file_type, file_size),
            )


async def update_document_status(
    doc_id: str,
    status: str,
    chunk_count: Optional[int] = None,
    error_message: Optional[str] = None,
) -> None:
    pool = get_mysql_pool()
    if pool is None:
        return
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "UPDATE kb_documents SET status = %s, chunk_count = %s, error_message = %s WHERE doc_id = %s",
                (status, chunk_count or 0, error_message, doc_id),
            )


async def get_document(doc_id: str, user_id: int) -> Optional[dict]:
    """获取文档详情，仅当文档属于该用户时返回。"""
    pool = get_mysql_pool()
    if pool is None:
        return None
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "SELECT doc_id, user_id, file_name, file_type, file_size, status, "
                "chunk_count, error_message, created_at "
                "FROM kb_documents WHERE doc_id = %s AND user_id = %s",
                (doc_id, user_id),
            )
            row = await cur.fetchone()
            if row is None:
                return None
            return {
                "doc_id": row[0],
                "user_id": row[1],
                "file_name": row[2],
                "file_type": row[3],
                "file_size": row[4],
                "status": row[5],
                "chunk_count": row[6],
                "error_message": row[7],
                "created_at": row[8].strftime("%Y-%m-%d %H:%M:%S") if row[8] else "",
            }


async def list_documents(user_id: int) -> list[dict]:
    pool = get_mysql_pool()
    if pool is None:
        return []
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "SELECT doc_id, file_name, file_type, file_size, status, "
                "chunk_count, error_message, created_at "
                "FROM kb_documents WHERE user_id = %s ORDER BY created_at DESC",
                (user_id,),
            )
            rows = await cur.fetchall()
            return [
                {
                    "doc_id": r[0],
                    "file_name": r[1],
                    "file_type": r[2],
                    "file_size": r[3],
                    "status": r[4],
                    "chunk_count": r[5],
                    "error_message": r[6],
                    "created_at": r[7].strftime("%Y-%m-%d %H:%M:%S") if r[7] else "",
                }
                for r in rows
            ]


async def count_documents(user_id: int) -> int:
    pool = get_mysql_pool()
    if pool is None:
        return 0
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "SELECT COUNT(*) FROM kb_documents WHERE user_id = %s",
                (user_id,),
            )
            row = await cur.fetchone()
            return row[0] if row else 0


async def delete_document(doc_id: str, user_id: int) -> None:
    pool = get_mysql_pool()
    if pool is None:
        return
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "DELETE FROM kb_documents WHERE doc_id = %s AND user_id = %s",
                (doc_id, user_id),
            )
