"""题库 / 答题 / 报告数据访问层"""

from __future__ import annotations

import json
from typing import Optional

import structlog
from fastapi import HTTPException

from app.core.db import get_mysql_pool
from app.repositories.rag_index_repository import transaction
from app.repositories import job_repository as jobs

logger = structlog.get_logger()


async def publish_generated_quiz(context, output):
    """Lock source revisions before the job, matching index publication's lock order."""
    async with transaction() as cur:
        for doc_id, revision, version in sorted(context.payload['scope']):
            await cur.execute('SELECT m.active,m.revision,m.index_version,d.status FROM kb_index_meta m '
                              'JOIN kb_documents d ON d.doc_id=m.doc_id WHERE m.doc_id=%s AND m.user_id=%s AND d.user_id=%s FOR UPDATE',
                              (doc_id, context.user_id, context.user_id))
            meta = await cur.fetchone()
            if (not meta or not meta['active'] or meta['revision'] != revision or meta['index_version'] != version
                    or meta['status'] != 'ready'):
                raise HTTPException(409, '材料版本已变化，未发布练习，请重新生成')
        job = await jobs.running(cur, context.task_id, context.lease_token)
        if job['kind'] != 'quiz' or job['user_id'] != context.user_id or job['payload_json'] != context.payload:
            raise jobs.TaskLeaseLost()
        quiz_id = 'quiz_' + context.task_id.removeprefix('job_')
        await cur.execute('INSERT INTO quiz_sessions(quiz_id,user_id,title,summary,user_input,questions_json) VALUES(%s,%s,%s,%s,%s,%s)',
                          (quiz_id, context.user_id, output.title, output.summary, context.payload['query'],
                           json.dumps([q.model_dump() for q in output.questions], ensure_ascii=False)))
        # Generic task APIs must never return answer-bearing question checkpoints.
        result = {'quiz_id': quiz_id, 'title': output.title}
        await jobs.publish_result(cur, job, result)
        return result


async def complete_quiz(quiz_id: str, user_id: int, records: list, score: dict, report: dict, context=None) -> dict:
    async with transaction() as cur:
        job = await jobs.running(cur, context.task_id, context.lease_token) if context else None
        if job and (job['kind'] != 'report' or job['user_id'] != user_id or job['payload_json']['quiz_id'] != quiz_id):
            raise jobs.TaskLeaseLost()
        await cur.execute("SELECT quiz_id FROM quiz_sessions WHERE quiz_id=%s AND user_id=%s FOR UPDATE", (quiz_id, user_id))
        if await cur.fetchone() is None:
            raise HTTPException(404, "练习不存在")
        await cur.execute("SELECT report_json FROM reports WHERE quiz_id=%s AND user_id=%s", (quiz_id, user_id))
        previous = await cur.fetchone()
        if previous:
            report = json.loads(previous['report_json']) if isinstance(previous['report_json'], str) else previous['report_json']
        else:
            await cur.execute("INSERT INTO answer_records (quiz_id,user_id,records_json,total_questions,correct_count,accuracy) VALUES (%s,%s,%s,%s,%s,%s)",
                              (quiz_id,user_id,json.dumps(records, ensure_ascii=False),score["total"],score["correct"],score["accuracy"]))
            await cur.execute("INSERT INTO reports (quiz_id,user_id,report_json) VALUES (%s,%s,%s)",
                              (quiz_id,user_id,json.dumps(report, ensure_ascii=False)))
            await cur.execute("UPDATE users SET total_xp=total_xp+%s WHERE id=%s", (10 + score["correct"] * 2, user_id))
        if job:
            await jobs.publish_result(cur, job, report)
        return report


async def save_quiz_session(
    quiz_id: str,
    user_id: Optional[int],
    title: str,
    summary: str,
    user_input: str,
    questions_json: list,
) -> None:
    pool = get_mysql_pool()
    if pool is None:
        raise HTTPException(503, "学习记录暂时不可用")
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "INSERT INTO quiz_sessions (quiz_id, user_id, title, summary, user_input, questions_json) "
                "VALUES (%s, %s, %s, %s, %s, %s)",
                (
                    quiz_id,
                    user_id,
                    title,
                    summary,
                    user_input,
                    json.dumps(questions_json, ensure_ascii=False),
                ),
            )


async def save_answer_record(
    quiz_id: str,
    user_id: Optional[int],
    records_json: list,
    total_questions: int,
    correct_count: int,
    accuracy: float,
) -> None:
    pool = get_mysql_pool()
    if pool is None:
        raise HTTPException(503, "学习记录暂时不可用")
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "INSERT INTO answer_records (quiz_id, user_id, records_json, total_questions, correct_count, accuracy) "
                "VALUES (%s, %s, %s, %s, %s, %s)",
                (
                    quiz_id,
                    user_id,
                    json.dumps(records_json, ensure_ascii=False),
                    total_questions,
                    correct_count,
                    accuracy,
                ),
            )


async def save_report(
    quiz_id: str,
    user_id: Optional[int],
    report_json: dict,
) -> None:
    pool = get_mysql_pool()
    if pool is None:
        raise HTTPException(503, "学习记录暂时不可用")
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "INSERT INTO reports (quiz_id, user_id, report_json) VALUES (%s, %s, %s)",
                (
                    quiz_id,
                    user_id,
                    json.dumps(report_json, ensure_ascii=False),
                ),
            )


async def get_user_quiz_count(user_id: int) -> int:
    pool = get_mysql_pool()
    if pool is None:
        return 0
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "SELECT COUNT(*) FROM quiz_sessions WHERE user_id = %s",
                (user_id,),
            )
            row = await cur.fetchone()
            return row[0] if row else 0


async def get_user_answer_stats(user_id: int) -> dict:
    """获取用户答题统计：总答对题数、平均正确率。"""
    pool = get_mysql_pool()
    if pool is None:
        return {"correct_count": 0, "average_accuracy": 0}
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "SELECT COALESCE(SUM(correct_count), 0), COALESCE(AVG(accuracy), 0) "
                "FROM answer_records WHERE user_id = %s",
                (user_id,),
            )
            row = await cur.fetchone()
            return {
                "correct_count": int(row[0]) if row else 0,
                "average_accuracy": round(float(row[1])) if row else 0,
            }


async def get_user_quiz_list(user_id: int, page: int, page_size: int) -> tuple[list[dict], int]:
    """分页获取用户闯关历史。返回 (items, total)。"""
    pool = get_mysql_pool()
    if pool is None:
        return [], 0
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            # 总数
            await cur.execute(
                "SELECT COUNT(*) FROM quiz_sessions WHERE user_id = %s",
                (user_id,),
            )
            total = (await cur.fetchone())[0]

            # 列表
            offset = (page - 1) * page_size
            await cur.execute(
                "SELECT qs.quiz_id, qs.title, "
                "COALESCE(ar.accuracy, 0), COALESCE(ar.total_questions, 0), "
                "qs.created_at "
                "FROM quiz_sessions qs "
                "LEFT JOIN answer_records ar ON qs.quiz_id = ar.quiz_id "
                "WHERE qs.user_id = %s "
                "ORDER BY qs.created_at DESC "
                "LIMIT %s OFFSET %s",
                (user_id, page_size, offset),
            )
            rows = await cur.fetchall()
            items = [
                {
                    "quiz_id": r[0],
                    "title": r[1],
                    "accuracy": float(r[2]),
                    "question_count": r[3],
                    "created_at": r[4].strftime("%Y-%m-%d %H:%M:%S") if r[4] else "",
                }
                for r in rows
            ]
            return items, total


async def get_quiz_detail(quiz_id: str, user_id: int) -> Optional[dict]:
    """获取单次闯关完整详情。"""
    pool = get_mysql_pool()
    if pool is None:
        return None
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "SELECT quiz_id, title, summary, user_input, questions_json, created_at "
                "FROM quiz_sessions WHERE quiz_id = %s AND user_id = %s",
                (quiz_id, user_id),
            )
            qs_row = await cur.fetchone()
            if qs_row is None:
                return None

            result = {
                "quiz_id": qs_row[0],
                "title": qs_row[1],
                "summary": qs_row[2],
                "user_input": qs_row[3],
                "questions": json.loads(qs_row[4]) if isinstance(qs_row[4], str) else qs_row[4],
                "created_at": qs_row[5].strftime("%Y-%m-%d %H:%M:%S") if qs_row[5] else "",
            }

            # 答题记录
            await cur.execute(
                "SELECT records_json FROM answer_records WHERE quiz_id = %s",
                (quiz_id,),
            )
            ar_row = await cur.fetchone()
            if ar_row:
                result["answer_records"] = json.loads(ar_row[0]) if isinstance(ar_row[0], str) else ar_row[0]

            # 报告
            await cur.execute(
                "SELECT report_json FROM reports WHERE quiz_id = %s",
                (quiz_id,),
            )
            rp_row = await cur.fetchone()
            if rp_row:
                result["report"] = json.loads(rp_row[0]) if isinstance(rp_row[0], str) else rp_row[0]

            return result
