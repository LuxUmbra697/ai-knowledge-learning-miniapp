"""出题 Chain"""

import re

from langchain_core.prompts import ChatPromptTemplate

from app.llm.langchain_factory import get_chat_model
from app.llm.structured_stage import run_json_stage
from app.models.quiz import QuizOutput
from app.prompts.quiz_prompt import QUIZ_HUMAN_PROMPT, QUIZ_SYSTEM_PROMPT, SEARCH_CONTEXT_TEMPLATE

def validate_quiz(data, question_count, difficulty):
    result = QuizOutput.model_validate(data)
    if len(result.questions) != question_count:
        raise ValueError(f'Expected exactly {question_count} questions')
    if len({q.id for q in result.questions}) != question_count:
        raise ValueError('Question IDs must be unique')
    if len({re.sub(r'\s+', '', q.stem) for q in result.questions}) != question_count:
        raise ValueError('Question stems must be distinct')
    if {q.type for q in result.questions} != {'single', 'multiple', 'judge'}:
        raise ValueError('Include single-choice, multiple-choice and judgment questions')
    if not result.title.strip() or len(result.title) > 120 or not result.summary.strip() or len(result.summary) > 800:
        raise ValueError('Title/summary must be nonempty and within the display limits')
    for question in result.questions:
        if not question.id.strip() or len(question.id) > 64:
            raise ValueError('Question IDs must contain 1-64 characters for the submission API')
        keys = [option.key for option in question.options]
        if not 2 <= len(keys) <= 6 or len(set(keys)) != len(keys) or any(not re.fullmatch('[A-F]', key) for key in keys):
            raise ValueError('Each question needs 2-6 distinct option keys A-F')
        if any(not option.text.strip() or len(option.text) > 800 for option in question.options):
            raise ValueError('Option text must contain 1-800 characters')
        if len({re.sub(r'\s+', '', option.text) for option in question.options}) != len(keys):
            raise ValueError('Option text must be distinct within each question')
        answers = set(question.answer)
        if not answers or len(answers) != len(question.answer) or not answers.issubset(keys):
            raise ValueError('Answers must be distinct existing option keys')
        if question.type == 'multiple' and len(answers) < 2 or question.type != 'multiple' and len(answers) != 1:
            raise ValueError('Answer cardinality does not match question type')
        if question.type == 'judge' and [(option.key, option.text.strip()) for option in question.options] != [('A', '正确'), ('B', '错误')]:
            raise ValueError('Judgment options must be A 正确 and B 错误')
        for field, maximum in (('stem', 1600), ('explanation', 2400), ('knowledge_point', 120)):
            value = getattr(question, field)
            if not value.strip() or len(value) > maximum:
                raise ValueError(f'{field} must contain 1-{maximum} characters')
        if question.image_url:
            raise ValueError('Image URLs may only be attached by the server image service')
        if difficulty != 'mixed' and question.difficulty != difficulty:
            raise ValueError('Question difficulty must match the requested difficulty')
    return result


async def generate_quiz(
    user_input: str,
    question_count: int = 5,
    difficulty: str = "mixed",
    search_context: str = "",
    context=None,
    private_source=False,
) -> QuizOutput:
    llm = get_chat_model(temperature=0.4)

    # 构建搜索上下文段落
    search_context_section = (
        SEARCH_CONTEXT_TEMPLATE.format(search_context=search_context)
        if search_context
        else ""
    )

    system = QUIZ_SYSTEM_PROMPT + (' 本次是私人学习材料，只允许依据所给材料出题；不得用常识补齐材料中未提供的事实。' if private_source else '')
    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", system),
            ("human", QUIZ_HUMAN_PROMPT + '\n{validation_feedback}'),
        ]
    )

    chain = prompt | llm

    values = {'user_input': user_input, 'question_count': question_count, 'difficulty': difficulty,
              'search_context_section': search_context_section}
    async def invoke(feedback):
        return await chain.ainvoke({**values, 'validation_feedback': feedback})
    return await run_json_stage(invoke, lambda data: validate_quiz(data, question_count, difficulty), stage='quiz', context=context,
                                input_bytes=lambda feedback: len((system + QUIZ_HUMAN_PROMPT.format(**values) + feedback).encode()))
