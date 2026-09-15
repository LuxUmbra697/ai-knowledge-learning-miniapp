"""Authoritative, idempotent question submissions and answer disclosure."""

import json
import aiomysql

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field

from app.core.db import get_mysql_pool
from app.services.quiz_evidence_service import visible_question


class AnswerSubmission(BaseModel):
    model_config = ConfigDict(extra="forbid")
    question_id: str = Field(min_length=1, max_length=64)
    selected_answers: list[str] = Field(min_length=1, max_length=8)
    duration_ms: int = Field(default=0, ge=0, le=86400000)


def grade_answer(question: dict, selected: list[str], duration_ms: int) -> dict:
    options = {option["key"] for option in question["options"]}
    if (not selected or len(set(selected)) != len(selected) or not set(selected) <= options
            or (question["type"] != "multiple" and len(selected) != 1)):
        raise HTTPException(422, "答案选项无效")
    return {"question_id": question["id"], "selected_answers": sorted(selected),
            "is_correct": set(selected) == set(question["answer"]), "duration_ms": duration_ms}


def decode_json(value):
    return json.loads(value) if isinstance(value, str) else value


def public_quiz(data: dict, revealed: set[str] | None = None) -> dict:
    visible = revealed or set()
    return {**data, "questions": [
        dict(question) if question["id"] in visible else {
            key: value for key, value in question.items() if key not in ("answer", "explanation", "citations")
        } for question in data.get("questions", [])
    ]}


async def submit_question(quiz_id: str, user_id: int, submission: AnswerSubmission) -> dict:
    pool = get_mysql_pool()
    if pool is None:
        raise HTTPException(503, "学习记录服务暂不可用，请稍后重试")
    async with pool.acquire() as conn:
        await conn.begin()
        try:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                # The quiz row serializes submissions across devices, including retries.
                await cur.execute("SELECT questions_json FROM quiz_sessions WHERE quiz_id=%s AND user_id=%s FOR UPDATE", (quiz_id, user_id))
                row = await cur.fetchone()
                if not row:
                    raise HTTPException(404, "练习不存在")
                questions = decode_json(row['questions_json'])
                question = next((q for q in questions if q["id"] == submission.question_id), None)
                if question is None:
                    raise HTTPException(404, "题目不存在")
                record = grade_answer(question, submission.selected_answers, submission.duration_ms)
                await cur.execute("SELECT record_json FROM quiz_question_attempts WHERE quiz_id=%s AND user_id=%s AND question_id=%s",
                                  (quiz_id, user_id, submission.question_id))
                previous = await cur.fetchone()
                if previous:
                    saved = decode_json(previous['record_json'])
                    if saved["selected_answers"] != record["selected_answers"]:
                        raise HTTPException(409, "该题已作答，不能覆盖原记录")
                    record = saved
                else:
                    await cur.execute("INSERT INTO quiz_question_attempts (quiz_id,user_id,question_id,record_json) VALUES (%s,%s,%s,%s)",
                                      (quiz_id, user_id, submission.question_id, json.dumps(record, ensure_ascii=False)))
                    from app.services.learning_state_service import record_initial
                    await record_initial(cur, user_id, quiz_id, question, record)
                await conn.commit()
        except BaseException:
            try:
                if not conn.closed:
                    await conn.rollback()
            except Exception:
                conn.close()
            raise
    return {"record": record, "question": await visible_question(question, user_id), "replayed": bool(previous)}


async def get_attempts(quiz_id: str, user_id: int) -> list[dict]:
    pool = get_mysql_pool()
    if pool is None:
        raise HTTPException(503, "学习记录服务暂不可用")
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute("SELECT record_json FROM quiz_question_attempts WHERE quiz_id=%s AND user_id=%s ORDER BY created_at,question_id", (quiz_id, user_id))
            return [decode_json(row[0]) for row in await cur.fetchall()]
