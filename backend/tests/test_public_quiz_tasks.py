from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from app.models.quiz import QuizGenerateRequest
from app.services import quiz_service, quiz_task_service


@pytest.mark.asyncio
async def test_public_text_admission_uses_durable_queue_and_never_queries_private_corpus(monkeypatch):
    enqueue = AsyncMock(return_value={'task_id': 'job_public'})
    scoped = AsyncMock(side_effect=AssertionError('Public practice cannot inspect private material'))
    monkeypatch.setattr(quiz_task_service.jobs, 'enqueue', enqueue)
    monkeypatch.setattr(quiz_task_service.index, 'scoped_chunks', scoped)
    request = QuizGenerateRequest(user_input='Python 基础', question_counts={'single': 1, 'fill': 1})
    result = await quiz_service.create_quiz_task(request, 17, 'public-practice-key')
    assert result.task_id == 'job_public'
    payload = enqueue.await_args.args[2]
    assert payload['scope'] == [] and payload['doc_ids'] == []
    assert payload['question_counts'] == {'single': 1, 'multiple': 0, 'judge': 0, 'fill': 1, 'written': 0}
    assert enqueue.await_args.args[3] == 'public-practice-key'
    scoped.assert_not_awaited()


@pytest.mark.asyncio
async def test_public_worker_preserves_budget_context_without_private_retrieval(monkeypatch):
    context = SimpleNamespace(user_id=17, payload={'query': 'Python', 'scope': [], 'doc_ids': [], 'question_count': 1, 'difficulty': 'easy'},
                              checkpoints={'quiz_sources': ''}, checkpoint=AsyncMock())
    generate = AsyncMock(return_value=SimpleNamespace(questions=[{}]))
    publish = AsyncMock(return_value={'quiz_id': 'quiz_public'})
    monkeypatch.setattr(quiz_task_service, 'generate_quiz', generate)
    monkeypatch.setattr(quiz_task_service.quiz_repository, 'publish_generated_quiz', publish)
    monkeypatch.setattr(quiz_task_service.retrieval_service, 'retrieve', AsyncMock(side_effect=AssertionError('private retrieval')))
    result = await quiz_task_service.run(context)
    assert result['quiz_id'] == 'quiz_public'
    assert generate.await_args.kwargs['context'] is context
    assert generate.await_args.kwargs['private_source'] is False
