"""闯关历史服务"""

from __future__ import annotations

from app.models.user import QuizHistoryItem, QuizHistoryList, QuizDetailResponse
from app.repositories import quiz_repository
from app.services.grading_service import get_attempts, public_quiz
from app.services.quiz_evidence_service import visible_question


async def get_quiz_history(user_id: int, page: int = 1, page_size: int = 10) -> QuizHistoryList:
    """获取用户闯关历史列表。"""
    items, total = await quiz_repository.get_user_quiz_list(user_id, page, page_size)
    return QuizHistoryList(
        items=[QuizHistoryItem(**item) for item in items],
        total=total,
        page=page,
        page_size=page_size,
    )


async def get_quiz_detail(quiz_id: str, user_id: int) -> QuizDetailResponse | None:
    """获取单次闯关详情。"""
    detail = await quiz_repository.get_quiz_detail(quiz_id, user_id)
    if detail is None:
        return None
    attempts = detail.get("answer_records") or await get_attempts(quiz_id, user_id)
    detail = public_quiz(detail, {record["question_id"] for record in attempts})
    detail['questions'] = [await visible_question(question, user_id) for question in detail['questions']]
    detail["answer_records"] = attempts
    return QuizDetailResponse(**detail)
