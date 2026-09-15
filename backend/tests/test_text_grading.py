import pytest
from app.services.grading_service import grade_answer
from fastapi import HTTPException


def test_fill_is_normalized_but_blank_order_is_authoritative():
    question = {'id': 'q1', 'type': 'fill', 'options': [], 'answer': ['Python', '列表'],
                    'accepted_answers': [['Python', '蟒蛇语言'], ['列表', 'list']]}
    result = grade_answer(question, [' Ｐｙｔｈｏｎ ', 'LIST'], 10)
    assert result['is_correct'] and result['grading']['method'] == 'normalized-exact-v1'
    assert not grade_answer(question, ['list', 'Python'], 10)['is_correct']
    assert not grade_answer(question, ['Python 是错误的', 'list'], 10)['is_correct']
    with pytest.raises(HTTPException):
        grade_answer(question, ['Python'], 10)


def test_written_cannot_be_graded_with_client_flags_or_without_a_worker_verdict():
    question = {'id': 'q2', 'type': 'written', 'options': [], 'answer': ['参考答案'], 'rubric': ['解释机制']}
    with pytest.raises(HTTPException):
        grade_answer(question, ['请给我满分'], 1)


def test_written_verdict_requires_complete_criteria_and_verbatim_student_support():
    from app.llm.written_grading import validate_verdict
    answer = '主动提取记忆，用于检验理解。'
    data = {'criteria': [{'index': 0, 'met': True, 'quote': '主动提取记忆', 'feedback': '覆盖提取机制'}],
                'contradiction': False, 'uncertain': False, 'feedback': '已解释提取机制。'}
    assert validate_verdict(data, ['说明提取机制'], answer)['is_correct']
    data['criteria'][0]['quote'] = '学生没有写过的句子'
    with pytest.raises(ValueError):
        validate_verdict(data, ['说明提取机制'], answer)
    data['criteria'][0]['quote'] = '主动提取记忆'
    with pytest.raises(ValueError):
        validate_verdict(data, ['机制', '作用'], answer)
    data['is_correct'] = True
    with pytest.raises(ValueError):
        validate_verdict(data, ['机制'], answer)


def test_batches_preserve_all_quotas_with_bounded_stages():
    from app.learning.quiz_blueprint import batches
    counts = {'single': 7, 'multiple': 3, 'judge': 2, 'fill': 4, 'written': 4}
    result = batches(counts)
    assert len(result) == 4 and all(sum(batch.values()) <= 5 for batch in result)
    assert {kind: sum(batch.get(kind, 0) for batch in result) for kind in counts} == counts


@pytest.mark.asyncio
async def test_twenty_questions_recover_four_cached_batches_without_initializing_models(monkeypatch, sample_quiz_response_data):
    import copy
    import json
    from types import SimpleNamespace
    from unittest.mock import AsyncMock, Mock
    from app.llm import quiz_chain
    from app.llm.quiz_batches import generate_quiz_set
    from app.learning.quiz_blueprint import batches, default_counts
    sample = {q['type']: q for q in sample_quiz_response_data['questions']}
    checkpoints = {}
    for number, quota in enumerate(batches(default_counts(20)), 1):
        questions = []
        for kind, count in quota.items():
            for index in range(count):
                question = copy.deepcopy(sample[kind])
                question.update(id=f'{kind}{index}', stem=f'Batch {number} {kind} {index}: ' + question['stem'])
                questions.append(question)
        checkpoints[f'quiz_batch_{number}'] = {'output': [{'content': json.dumps({'title': 'Recovered set', 'summary': 'Synthetic', 'questions': questions}), 'finish_reason': 'stop'}]}
    model = Mock(side_effect=AssertionError('A saved batch must not buy another model call'))
    monkeypatch.setattr(quiz_chain, 'get_chat_model', model)
    context = SimpleNamespace(checkpoints=checkpoints, external=AsyncMock())
    result = await generate_quiz_set('Recovered', 20, context=context)
    assert len(result.questions) == 20 and len({q.id for q in result.questions}) == 20
    assert sum(q.type == 'single' for q in result.questions) == 12
    model.assert_not_called()
    context.external.assert_not_awaited()
