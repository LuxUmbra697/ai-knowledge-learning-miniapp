import pytest
from pydantic import ValidationError


def test_tutor_requests_never_accept_model_selected_identity_or_unbounded_modes():
    from app.models.tutor import TutorCreate, TutorTurn
    for data in ({'goal': 'Learn', 'doc_ids': ['doc_a'], 'user_id': 999}, {'goal': 'Learn', 'doc_ids': ['doc_a'], 'mode': 'shell'},
                 {'goal': 'Learn', 'doc_ids': []}, {'goal': 'Learn', 'mode': 'diagnosis', 'doc_ids': ['doc_a']}):
        with pytest.raises(ValidationError):
            TutorCreate.model_validate(data)
    with pytest.raises(ValidationError):
        TutorTurn.model_validate({'version': 0, 'message': 'My answer', 'tool': 'run_sql'})


def test_tutor_reply_keeps_a_single_question_exact_evidence_and_unconfirmed_diagnosis():
    from app.llm.tutor_chain import validate_reply
    evidence = [{'id': 'E1', 'content': '主动回忆可以暴露遗漏。'}]
    raw = {'status': 'hint', 'hint': '先试着回忆刚才读过的内容。', 'question': '不看笔记，你记得哪个概念？',
           'citations': [{'evidence_id': 'E1', 'quote': '主动回忆可以暴露遗漏'}], 'diagnosis': None, 'practice': None}
    result = validate_reply(raw, evidence, 'socratic', 1)
    assert result['status'] == 'hint'
    for changed in ({'question': '问题一？问题二？'}, {'hint': 'x' * 181}, {'citations': [{'evidence_id': 'E2', 'quote': '伪造引用'}]},
                    {'diagnosis': 'careless'}, {'status': 'no_evidence'}):
        with pytest.raises(ValueError):
            validate_reply({**raw, **changed}, evidence, 'socratic', 1)


def test_tutor_tool_arguments_reject_side_effects_paths_and_cross_owner_scope():
    from app.services.tutor_tools import TOOL_SCHEMAS
    for schema in TOOL_SCHEMAS.values():
        with pytest.raises(ValidationError):
            schema.model_validate({'user_id': 999, 'path': '../secret', 'sql': 'SELECT 1'})
    assert set(TOOL_SCHEMAS) == {'retrieve_notes', 'read_learning_state', 'review_queue', 'propose_practice'}


def test_tutor_can_decline_when_retrieved_material_does_not_support_the_question():
    from app.llm.tutor_chain import validate_reply
    output = {'status': 'no_evidence', 'hint': '资料不足，暂不推断。', 'question': '可以补充相关段落吗？', 'citations': [], 'diagnosis': None, 'practice': None}
    assert validate_reply(output, [{'id': 'E1', 'content': 'Unrelated context'}], 'socratic', 1)['status'] == 'no_evidence'
    with pytest.raises(ValueError):
        validate_reply({**output, 'question': '问题一？问题二？'}, [], 'socratic', 1)


def test_practice_confirmation_rejects_implicit_consent_and_changed_proposal():
    from app.models.tutor import TutorPracticeConfirm
    assert TutorPracticeConfirm(version=1, confirmed=True).confirmed
    for changed in ({'confirmed': False}, {'confirmed': 'true'}, {'version': True}, {'version': 7},
                    {'count': 20}, {'doc_id': 'other-document'}, {'user_id': 999}):
        with pytest.raises(ValidationError):
            TutorPracticeConfirm.model_validate({'version': 1, 'confirmed': True, **changed})


def test_diagnosis_includes_option_text_not_only_meaningless_answer_letters():
    from app.services.tutor_graph import practice_evidence
    value = practice_evidence({'question': {'stem': 'Question', 'options': [{'key': 'A', 'text': 'Small steps'}, {'key': 'B', 'text': 'Large steps'}],
                                          'answer': ['A'], 'explanation': 'Reference'}, 'record': {'selected_answers': ['B']}})
    assert 'A: Small steps' in value and 'B: Large steps' in value
    assert '学生作答：B' in value and '参考答案：A' in value


@pytest.mark.asyncio
async def test_tutor_tool_budget_and_proposal_never_generate_or_mutate_a_plan():
    from app.services.tutor_tools import TutorTools
    from fastapi import HTTPException
    tools = TutorTools(12, ('owned-document',), None)
    for _ in range(4):
        result = await tools.call('propose_practice', {'count': 2, 'focus': 'Public concept'})
        assert result['doc_id'] == 'owned-document' and result['requires_confirmation'] and not result['created']
    with pytest.raises(HTTPException) as error:
        await tools.call('propose_practice', {'count': 1, 'focus': 'Over budget'})
    assert error.value.status_code == 429
