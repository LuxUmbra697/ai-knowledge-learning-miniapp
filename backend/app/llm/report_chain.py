"""报告 Chain"""

import json
import re

from langchain_core.prompts import ChatPromptTemplate

from app.llm.langchain_factory import get_chat_model
from app.models.quiz import Question, AnswerRecord
from app.models.report import ReportOutput
from app.prompts.report_prompt import REPORT_HUMAN_PROMPT, REPORT_SYSTEM_PROMPT


def _extract_json(text: str) -> dict:
    """从 LLM 输出中提取 JSON，兼容 markdown 代码块包裹"""
    match = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    raw = match.group(1).strip() if match else text.strip()
    return json.loads(raw)


async def generate_report(
    topic: str,
    questions: list[Question],
    answer_records: list[AnswerRecord],
    score_summary: dict,
) -> ReportOutput:
    llm = get_chat_model(temperature=0.5)

    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", REPORT_SYSTEM_PROMPT),
            ("human", REPORT_HUMAN_PROMPT),
        ]
    )

    chain = prompt | llm

    result = await chain.ainvoke(
        {
            "topic": topic,
            "quiz_json": json.dumps(
                [q.model_dump() for q in questions], ensure_ascii=False
            ),
            "answer_records": json.dumps(
                [r.model_dump() for r in answer_records], ensure_ascii=False
            ),
            "score_summary": json.dumps(score_summary, ensure_ascii=False),
        }
    )

    data = _extract_json(result.content)
    return ReportOutput.model_validate(data)
