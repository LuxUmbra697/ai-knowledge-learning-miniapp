"""Quiz retries have one explicit ten-call ceiling, separate from other stages."""
from types import SimpleNamespace
from unittest.mock import AsyncMock
import copy
import json

import httpx
import pytest
from openai import APIStatusError

from app.llm.structured_stage import run_json_stage, StructuredGenerationError


def response(content):
    return SimpleNamespace(content=content, usage_metadata={'total_tokens': 1}, response_metadata={})


@pytest.mark.asyncio
async def test_quiz_can_repair_on_tenth_attempt_and_never_calls_eleventh(monkeypatch):
    monkeypatch.setattr('app.llm.structured_stage.asyncio.sleep', AsyncMock())
    invoke = AsyncMock(side_effect=[response('invalid')] * 9 + [response('{"ok":true}')])
    result = await run_json_stage(invoke, lambda value: value, stage='quiz', max_attempts=10)
    assert result == {'ok': True} and invoke.await_count == 10
    invoke = AsyncMock(return_value=response('invalid'))
    with pytest.raises(StructuredGenerationError, match='validation_failed'):
        await run_json_stage(invoke, lambda value: value, stage='quiz', max_attempts=10)
    assert invoke.await_count == 10


@pytest.mark.asyncio
async def test_nine_saved_failures_consume_budget_after_recovery(monkeypatch):
    monkeypatch.setattr('app.llm.structured_stage.asyncio.sleep', AsyncMock())
    history = [{'content': 'invalid'}] * 9
    context = SimpleNamespace(checkpoints={'quiz': {'output': history}})
    async def external(_stage, operation, _size):
        value, _tokens = await operation()
        return value
    context.external = AsyncMock(side_effect=external)
    invoke = AsyncMock(return_value=response('{"ok":true}'))
    assert await run_json_stage(invoke, lambda value: value, stage='quiz', context=context, max_attempts=10) == {'ok': True}
    assert invoke.await_count == context.external.await_count == 1


@pytest.mark.asyncio
@pytest.mark.parametrize('status,code', [(401, None), (403, None), (400, None), (429, 'insufficient_quota')])
async def test_quiz_ten_attempt_policy_still_stops_permanent_provider_errors(status, code):
    error = APIStatusError('do not disclose provider secrets', response=httpx.Response(status, request=httpx.Request('POST', 'https://provider.invalid')), body={'error': {'code': code}})
    invoke = AsyncMock(side_effect=error)
    with pytest.raises(StructuredGenerationError, match='provider_failed'):
        await run_json_stage(invoke, lambda value: value, stage='quiz', max_attempts=10)
    assert invoke.await_count == 1


@pytest.mark.asyncio
async def test_quiz_explicit_rate_limit_backoff_can_recover(monkeypatch):
    sleep = AsyncMock()
    monkeypatch.setattr('app.llm.structured_stage.asyncio.sleep', sleep)
    error = APIStatusError('rate limited', response=httpx.Response(429, headers={'retry-after': '2'}, request=httpx.Request('POST', 'https://provider.invalid')), body={'error': {'code': 'rate_limit_exceeded'}})
    invoke = AsyncMock(side_effect=[error, response('{"ok":true}')])
    assert await run_json_stage(invoke, lambda value: value, stage='quiz', max_attempts=10) == {'ok': True}
    sleep.assert_awaited_once_with(2)


@pytest.mark.asyncio
async def test_cross_batch_duplicate_repairs_only_bad_batch_from_checkpoint(monkeypatch, sample_quiz_response_data):
    from langchain_core.runnables import RunnableLambda
    from app.llm import quiz_chain
    from app.llm.quiz_batches import generate_quiz_set
    from app.learning.quiz_blueprint import batches, default_counts
    templates = {q['type']: q for q in sample_quiz_response_data['questions']}
    saved = []
    for number, quota in enumerate(batches(default_counts(8))):
        questions = []
        for kind, count in quota.items():
            for _ in range(count):
                q = copy.deepcopy(templates[kind])
                q.update(id=f'q{len(questions)}', stem=f'Synthetic batch {number} question {len(questions)}')
                questions.append(q)
        saved.append(dict(title='Synthetic', summary='Duplicate regression', questions=questions))
    repaired = copy.deepcopy(saved[1])
    saved[1]['questions'][0]['stem'] = saved[0]['questions'][0]['stem']
    context = SimpleNamespace(checkpoints={f'quiz_batch_{i+1}': {'output': [{'content': json.dumps(data), 'finish_reason': 'stop'}]} for i, data in enumerate(saved)})
    async def external(_stage, operation, _size):
        value, _tokens = await operation()
        return value
    context.external = AsyncMock(side_effect=external)
    invoke = AsyncMock(return_value=response(json.dumps(repaired)))
    monkeypatch.setattr(quiz_chain, 'get_chat_model', lambda **_: RunnableLambda(invoke))
    monkeypatch.setattr('app.llm.structured_stage.asyncio.sleep', AsyncMock())
    output = await generate_quiz_set('Synthetic duplicate regression', 8, context=context)
    assert len(output.questions) == len({q.stem for q in output.questions}) == 8
    assert invoke.await_count == context.external.await_count == 1
    assert context.external.await_args.args[0] == 'quiz_batch_2'
