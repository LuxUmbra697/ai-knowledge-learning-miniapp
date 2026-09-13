"""报告服务"""

from typing import Optional

import structlog

from app.core.exceptions import ReportGenerationError
from app.llm.report_chain import generate_report
from app.models.report import ReportGenerateRequest, ReportGenerateResponse
from app.services.scoring_service import compute_score_summary
from app.repositories import quiz_repository
from fastapi import HTTPException
from app.models.quiz import Question, AnswerRecord
from app.services.grading_service import get_attempts

logger = structlog.get_logger()


async def handle_report_generate(
    req: ReportGenerateRequest,
    user_id: Optional[int] = None,
) -> ReportGenerateResponse:
    detail = await quiz_repository.get_quiz_detail(req.quiz_id, user_id)
    if detail is None:
        raise HTTPException(404, "练习不存在")
    if detail.get("report"):
        return ReportGenerateResponse.model_validate(detail["report"])
    records = await get_attempts(req.quiz_id, user_id)
    questions = [Question.model_validate(q) for q in detail["questions"]]
    if {record["question_id"] for record in records} != {q.id for q in questions}:
        raise HTTPException(409, "请完成所有题目后再生成报告")
    answer_records = [AnswerRecord.model_validate(record) for record in records]
    score_summary = compute_score_summary(answer_records)

    try:
        report_output = await generate_report(
            topic=detail["title"],
            questions=questions,
            answer_records=answer_records,
            score_summary=score_summary,
        )
    except Exception as e:
        logger.error("report_generation_failed", error_type=type(e).__name__)
        raise ReportGenerationError("报告生成暂不可用，答题记录已保存，请稍后重试") from e

    report_output.accuracy = score_summary["accuracy"]
    saved = await quiz_repository.complete_quiz(
        req.quiz_id, user_id, records, score_summary, report_output.model_dump())
    return ReportGenerateResponse.model_validate(saved)
