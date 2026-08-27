"""出题 Chain"""

import json
import re

import structlog
from langchain_core.prompts import ChatPromptTemplate

from app.llm.langchain_factory import get_chat_model
from app.models.quiz import QuizOutput
from app.prompts.quiz_prompt import QUIZ_HUMAN_PROMPT, QUIZ_SYSTEM_PROMPT, SEARCH_CONTEXT_TEMPLATE

logger = structlog.get_logger()


def _extract_json(text: str) -> dict:
    """从 LLM 输出中提取 JSON，兼容 markdown 代码块包裹"""
    # 尝试提取 ```json ... ``` 包裹的内容
    match = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    raw = match.group(1).strip() if match else text.strip()
    return json.loads(raw)


async def generate_quiz(
    user_input: str,
    question_count: int = 5,
    difficulty: str = "mixed",
    search_context: str = "",
) -> QuizOutput:
    llm = get_chat_model(temperature=0.4)

    # 构建搜索上下文段落
    search_context_section = (
        SEARCH_CONTEXT_TEMPLATE.format(search_context=search_context)
        if search_context
        else ""
    )

    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", QUIZ_SYSTEM_PROMPT),
            ("human", QUIZ_HUMAN_PROMPT),
        ]
    )

    chain = prompt | llm

    result = await chain.ainvoke(
        {
            "user_input": user_input,
            "question_count": question_count,
            "difficulty": difficulty,
            "search_context_section": search_context_section,
        }
    )

    content = result.content
    logger.debug("llm_quiz_raw_response", content_length=len(content), content_preview=content[:200] if content else "<empty>")

    if not content:
        raise ValueError("LLM 返回内容为空")

    data = _extract_json(content)
    return QuizOutput.model_validate(data)
