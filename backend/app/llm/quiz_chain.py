"""出题 Chain"""

import json
import re

from langchain_core.prompts import ChatPromptTemplate

from app.llm.langchain_factory import get_chat_model
from app.llm.structured_stage import run_json_stage
from app.models.quiz import QuizOutput, QuestionCitation
from app.models.evidence import Evidence
from app.prompts.quiz_prompt import QUIZ_HUMAN_PROMPT, QUIZ_SYSTEM_PROMPT, SEARCH_CONTEXT_TEMPLATE

def validate_quiz(data, question_count, difficulty, evidence=None):
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
    owned = {item.id: item for item in (Evidence.model_validate(row) for row in (evidence or []))}
    covered = set()
    for raw, question in zip(data['questions'], result.questions):
        if evidence is not None and not question.citations:
            raise ValueError('Every private question requires 1-3 exact source citations')
        seen = set()
        canonical = []
        for citation, original in zip(question.citations, raw.get('citations', [])):
            if set(original) != {'evidence_id', 'quote'}:
                raise ValueError('A generated citation may contain only evidence_id and quote; locations are server-owned')
            item = owned.get(citation.evidence_id)
            pair = (citation.evidence_id, citation.quote)
            if item is None or not citation.quote.strip() or citation.quote not in item.content or pair in seen:
                raise ValueError('Citations require distinct available IDs and exact nonblank source substrings')
            seen.add(pair)
            covered.add(item.id)
            canonical.append(QuestionCitation(evidence_id=item.id, quote=citation.quote,
                **item.model_dump(include={'doc_id', 'chunk_id', 'revision', 'index_version', 'file_name', 'page', 'section'})))
        question.citations = canonical
    if evidence is not None and (not owned or len(covered) < min(2, len(owned))):
        raise ValueError('Cover at least two supplied evidence fragments, or the sole fragment when only one is supplied')
    return result


async def generate_quiz(
    user_input: str,
    question_count: int = 5,
    difficulty: str = "mixed",
    search_context: str = "",
    context=None,
    private_source=False,
) -> QuizOutput:

    # 构建搜索上下文段落
    search_context_section = (
        SEARCH_CONTEXT_TEMPLATE.format(search_context=search_context)
        if search_context
        else ""
    )

    evidence = None
    if private_source:
        source = json.loads(search_context)
        if source.get('source_type') != 'private_document' or not source.get('evidence'):
            raise ValueError('Private practice requires structured source evidence')
        evidence = source['evidence']
    system = QUIZ_SYSTEM_PROMPT + (''' 本次是私人学习材料，只允许依据所给材料出题；不得用常识补齐材料中未提供的事实。
每道题必须增加 citations 数组，包含 1 至 3 个对象，每个对象仅有 evidence_id 和 quote 两个字段。
evidence_id 必须是材料中的 id，quote 为对应 content 中逐字存在的 2 至 500 字摘录，直接支持本题答案与解析。
不得自行填写文档路径、页码或其他位置字段。全套题至少覆盖两个所给片段；若仅有一个片段则覆盖该片段。
引用校验是必要条件，不代表事实证明；不为增加题型而编造材料未支持的知识。''' if private_source else '')
    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", system),
            ("human", QUIZ_HUMAN_PROMPT + '\n{validation_feedback}'),
        ]
    )

    chain = None
    def prepare():
        nonlocal chain
        if chain is None:
            chain = prompt | get_chat_model(temperature=0.4)

    values = {'user_input': user_input, 'question_count': question_count, 'difficulty': difficulty,
              'search_context_section': search_context_section}
    async def invoke(feedback):
        return await chain.ainvoke({**values, 'validation_feedback': feedback})
    return await run_json_stage(invoke, lambda data: validate_quiz(data, question_count, difficulty, evidence), stage='quiz', context=context,
                                input_bytes=lambda feedback: len((system + QUIZ_HUMAN_PROMPT.format(**values) + feedback).encode()), prepare=prepare)
