"""Exact, bounded exercise blueprints, independent of provider availability."""
import copy

import pytest
from app.llm.quiz_chain import validate_quiz
from app.models.quiz import QuizGenerateRequest
from app.services.grading_service import public_quiz
from pydantic import ValidationError


def test_total_and_per_type_counts_are_independently_configurable():
    request = QuizGenerateRequest(user_input='Practice', question_counts={'single': 2, 'fill': 1, 'written': 1})
    assert request.question_count == 4
    assert request.question_counts.model_dump() == {'single': 2, 'multiple': 0, 'judge': 0, 'fill': 1, 'written': 1}
    assert QuizGenerateRequest(user_input='Practice', question_count=1).question_count == 1
    assert QuizGenerateRequest(user_input='Practice', question_count=20).question_count == 20


@pytest.mark.parametrize('counts,total', [({'single': 0}, None), ({'single': -1}, None),
    ({'single': 21}, None), ({'single': True}, None), ({'single': 2.5}, None),
    ({'single': 1, 'multiple': 1}, 3), ({'unknown': 1}, None), ({'written': 10, 'fill': 11}, None)])
def test_invalid_blueprints_never_reach_a_provider(counts, total):
    values = {'user_input': 'Practice', 'question_counts': counts}
    if total is not None:
        values['question_count'] = total
    with pytest.raises(ValidationError):
        QuizGenerateRequest(**values)


def test_requested_distribution_is_exact_and_may_contain_only_one_type(sample_quiz_response_data):
    data = copy.deepcopy(sample_quiz_response_data)
    data['questions'] = data['questions'][:2]
    assert len(validate_quiz(data, 2, 'mixed', question_counts={'single': 2}).questions) == 2
    with pytest.raises(ValueError, match='distribution'):
        validate_quiz(data, 2, 'mixed', question_counts={'single': 1, 'judge': 1})


def test_text_questions_keep_answer_variants_and_rubric_private_in_contract():
    base = {'id': 'q1', 'stem': '请填写学习方法：___', 'type': 'fill', 'options': [], 'answer': ['主动回忆'],
                'accepted_answers': [['主动回忆', '主动检索']], 'explanation': '通过提取检查记忆。',
                'knowledge_point': '主动回忆', 'difficulty': 'easy'}
    data = {'title': '学习方法', 'summary': '练习', 'questions': [base]}
    result = validate_quiz(data, 1, 'mixed', question_counts={'fill': 1})
    assert result.questions[0].accepted_answers == [['主动回忆', '主动检索']]
    base['accepted_answers'] = [['重新阅读']]
    with pytest.raises(ValueError, match='canonical'):
        validate_quiz(data, 1, 'mixed', question_counts={'fill': 1})
    base.update(type='written', stem='解释主动回忆的用途', answer=['通过主动提取检查理解与记忆。'],
                accepted_answers=[], rubric=['指出主动提取，而非重复阅读', '说明检验理解或记忆的目的'])
    assert validate_quiz(data, 1, 'mixed', question_counts={'written': 1}).questions[0].rubric
    hidden = public_quiz(data)['questions'][0]
    assert not {'answer', 'accepted_answers', 'rubric', 'explanation', 'citations'} & hidden.keys()
    assert public_quiz(data, {'q1'})['questions'][0]['rubric']


@pytest.mark.parametrize('change', [{'options': [{'key': 'A', 'text': '答案'}]}, {'answer': []},
    {'accepted_answers': []}, {'accepted_answers': [['主动回忆']] * 5}])
def test_fill_contract_rejects_malformed_answers(change):
    question = {'id': 'q1', 'stem': '学习方法：___', 'type': 'fill', 'options': [], 'answer': ['主动回忆'],
                    'accepted_answers': [['主动回忆']], 'explanation': '提取练习', 'knowledge_point': '回忆', 'difficulty': 'easy'}
    question.update(change)
    with pytest.raises(ValueError):
        validate_quiz({'title': '学习', 'summary': '练习', 'questions': [question]}, 1, 'mixed', question_counts={'fill': 1})
