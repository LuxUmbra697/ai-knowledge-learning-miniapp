import asyncio
import uuid

import pytest
from app.repositories import quiz_repository as quizzes
from app.repositories.rag_index_repository import transaction
from app.services.grading_service import AnswerSubmission, submit_question
from app.services.learning_map_service import get_map
from fastapi import HTTPException


@pytest.mark.asyncio
async def test_map_is_owned_complete_persisted_and_replayed(users):
    quiz = 'quiz_' + uuid.uuid4().hex
    question = {'id': 'q1', 'type': 'single', 'stem': '选择主动回忆', 'options': [{'key': 'A', 'text': '主动提取'}, {'key': 'B', 'text': '被动重读'}],
                'answer': ['A'], 'explanation': '主动提取记忆', 'knowledge_point': '主动回忆', 'difficulty': 'easy'}
    await quizzes.save_quiz_session(quiz, users[0], '合成梳理图', 'Synthetic', 'Synthetic', [question])
    for user, code in [(users[0], 409), (users[1], 404)]:
        with pytest.raises(HTTPException) as error:
            await get_map(quiz, user)
        assert error.value.status_code == code
    await submit_question(quiz, users[0], AnswerSubmission(question_id='q1', selected_answers=['B']))
    first, replay = await asyncio.gather(get_map(quiz, users[0]), get_map(quiz, users[0]))
    assert first == replay
    assert any(n['kind'] == 'question' and n['state'] == 'wrong' for n in first['nodes'])
    async with transaction() as cur:
        await cur.execute('SELECT COUNT(*) AS n FROM quiz_learning_maps WHERE quiz_id=%s AND user_id=%s', (quiz, users[0]))
        assert (await cur.fetchone())['n'] == 1
    with pytest.raises(HTTPException) as error:
        await get_map(quiz, users[1])
    assert error.value.status_code == 404


@pytest.mark.asyncio
async def test_deleted_source_disappears_from_persisted_map(users):
    from app.repositories import rag_index_repository as index
    from langchain_core.documents import Document
    text = '主动回忆通过提取记忆检验理解。'
    doc_id, quiz_id = 'doc_' + uuid.uuid4().hex, 'quiz_' + uuid.uuid4().hex
    await index.reserve(doc_id, users[0], '合成原文.md', 'md', len(text.encode()), uuid.uuid4().hex * 2, 'map-test-v1', 10)
    await index.publish(doc_id, users[0], 1, 'map-test-v1', [Document(page_content=text, metadata={'chunk_id': 'map-source'})])
    question = {'id': 'q1', 'type': 'judge', 'stem': '主动回忆可以检验理解。', 'options': [{'key': 'A', 'text': '正确'}, {'key': 'B', 'text': '错误'}],
                'answer': ['A'], 'explanation': text, 'knowledge_point': '主动回忆', 'difficulty': 'easy',
                'citations': [{'evidence_id': 'E1', 'status': 'verified', 'doc_id': doc_id, 'chunk_id': 'map-source', 'revision': 1,
                               'index_version': 'map-test-v1', 'quote': text, 'file_name': '合成原文.md'}]}
    await quizzes.save_quiz_session(quiz_id, users[0], '合成引用图', 'Synthetic', 'Synthetic', [question])
    await submit_question(quiz_id, users[0], AnswerSubmission(question_id='q1', selected_answers=['A']))
    before = await get_map(quiz_id, users[0])
    assert len([n for n in before['nodes'] if n['kind'] == 'source']) == 1
    await index.tombstone(doc_id, users[0])
    after = await get_map(quiz_id, users[0])
    assert not any(n['kind'] == 'source' for n in after['nodes'])
    assert before['source_hash'] != after['source_hash']
