"""报告服务"""

from typing import Optional
import uuid

import structlog

from app.core.exceptions import ReportGenerationError
from app.llm.report_chain import generate_report
from app.models.report import ReportGenerateRequest, ReportGenerateResponse
from app.services.scoring_service import compute_score_summary
from app.repositories import quiz_repository
from app.repositories import job_repository as jobs
from app.services.learning_task_service import wait_result
from fastapi import HTTPException
from app.models.quiz import Question, AnswerRecord
from app.services.grading_service import get_attempts

logger = structlog.get_logger()


async def handle_report_generate(
    req: ReportGenerateRequest,
    user_id: Optional[int] = None,
    key: str | None = None,
) -> ReportGenerateResponse:
    task = await create_report_task(req, user_id, key)
    result = await wait_result(task['task_id'], user_id, seconds=60)
    return ReportGenerateResponse.model_validate(result)


async def report_inputs(req, user_id):
    detail = await quiz_repository.get_quiz_detail(req.quiz_id, user_id)
    if detail is None:
        raise HTTPException(404, "练习不存在")
    if detail.get('report'):
        return detail, []
    records = await get_attempts(req.quiz_id, user_id)
    if not detail['questions'] or {record["question_id"] for record in records} != {q['id'] for q in detail['questions']}:
        raise HTTPException(409, "请完成所有题目后再生成报告")
    return detail, records


async def create_report_task(req, user_id, key=None):
    detail, _records = await report_inputs(req, user_id)
    return await jobs.enqueue(user_id, 'report', {'quiz_id': req.quiz_id, 'title': detail['title']}, key or uuid.uuid4().hex)


async def run_report_task(context):
    req = ReportGenerateRequest(quiz_id=context.payload['quiz_id'])
    detail, records = await report_inputs(req, context.user_id)
    if detail.get('report'):
        return await quiz_repository.complete_quiz(req.quiz_id, context.user_id, records, {}, detail['report'], context=context)
    questions = [Question.model_validate(q) for q in detail['questions']]
    answer_records = [AnswerRecord.model_validate(record) for record in records]
    score_summary = compute_score_summary(answer_records)
    await context.checkpoint('report_input_validated', {'question_count': len(questions), 'submitted_count': len(records)})
    try:
        report_output = await generate_report(
            topic=detail["title"],
            questions=questions,
            answer_records=answer_records,
            score_summary=score_summary,
            context=context,
        )
    except (jobs.TaskLeaseLost, jobs.TaskBudgetExceeded):
        raise
    except Exception as e:
        logger.error("report_generation_failed", error_type=type(e).__name__)
        raise ReportGenerationError("报告生成暂不可用，答题记录已保存，请稍后重试") from e

    report_output.accuracy = score_summary["accuracy"]
    await context.checkpoint('report_validated', {'accuracy': report_output.accuracy})
    saved = await quiz_repository.complete_quiz(
        req.quiz_id, context.user_id, records, score_summary, report_output.model_dump(), context=context)
    return saved
