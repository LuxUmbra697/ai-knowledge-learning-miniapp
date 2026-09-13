"""报告 Chain"""

import json

from langchain_core.prompts import ChatPromptTemplate

from app.llm.langchain_factory import get_chat_model
from app.llm.structured_stage import run_json_stage
from app.models.quiz import Question, AnswerRecord
from app.models.report import ReportOutput
from app.prompts.report_prompt import REPORT_HUMAN_PROMPT, REPORT_SYSTEM_PROMPT


async def generate_report(
    topic: str,
    questions: list[Question],
    answer_records: list[AnswerRecord],
    score_summary: dict,
    context=None,
) -> ReportOutput:
    llm = get_chat_model(temperature=0.5)

    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", REPORT_SYSTEM_PROMPT),
            ("human", REPORT_HUMAN_PROMPT + '\n{validation_feedback}'),
        ]
    )

    chain = prompt | llm

    values = {
            "topic": topic,
            "quiz_json": json.dumps(
                [q.model_dump() for q in questions], ensure_ascii=False
            ),
            "answer_records": json.dumps(
                [r.model_dump() for r in answer_records], ensure_ascii=False
            ),
            "score_summary": json.dumps(score_summary, ensure_ascii=False),
        }
    async def invoke(feedback):
        return await chain.ainvoke({**values, 'validation_feedback': feedback})
    def validate(data):
        result = ReportOutput.model_validate(data)
        points = {question.knowledge_point for question in questions}
        if not set(result.mastered_points + result.weak_points).issubset(points):
            raise ValueError('Knowledge points must come from the submitted exercise')
        if len(result.three_line_summary) != 3 or not 1 <= len(result.advice) <= 6:
            raise ValueError('Include three summary lines and 1-6 next-step suggestions')
        if any(not value.strip() or len(value) > 1000 for value in [*result.three_line_summary, *result.advice, result.share_quote]):
            raise ValueError('Report text must be nonempty and bounded')
        result.accuracy = score_summary['accuracy']
        return result
    return await run_json_stage(invoke, validate, stage='report', context=context,
                                input_bytes=lambda feedback: len((REPORT_SYSTEM_PROMPT + REPORT_HUMAN_PROMPT.format(**values) + feedback).encode()))
