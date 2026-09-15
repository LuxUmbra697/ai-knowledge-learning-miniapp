from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
from openai import APIStatusError, APITimeoutError
import pytest

from app.llm.structured_stage import run_json_stage, StructuredGenerationError


def message(content, reason='stop'):
    return SimpleNamespace(content=content, usage_metadata={'total_tokens': 10}, response_metadata={'finish_reason': reason})


@pytest.mark.asyncio
async def test_invalid_json_is_repaired_with_bounded_diagnostics():
    invoke = AsyncMock(side_effect=[message('not json'), message('{"valid":true}')])
    result = await run_json_stage(invoke, lambda value: value, stage='quiz')
    assert result == {'valid': True} and invoke.await_count == 2
    assert invoke.await_args_list[0].args == ('',)
    assert '校验' in invoke.await_args_list[1].args[0]


@pytest.mark.asyncio
async def test_three_empty_or_truncated_responses_stop():
    invoke = AsyncMock(side_effect=[message(''), message('{}', 'length'), message('[]')])
    def validate(value):
        if not isinstance(value, dict):
            raise ValueError('Expected object')
        return value
    with pytest.raises(StructuredGenerationError, match='three_attempts'):
        await run_json_stage(invoke, validate, stage='quiz')
    assert invoke.await_count == 3


@pytest.mark.asyncio
@pytest.mark.parametrize('status', [400, 401, 403, 404, 429])
async def test_permanent_failure_is_not_retried_or_disclosed(status):
    response = httpx.Response(status, request=httpx.Request('POST', 'https://provider.invalid'))
    invoke = AsyncMock(side_effect=APIStatusError('private diagnostics', response=response, body=None))
    with pytest.raises(StructuredGenerationError, match='^provider_failed$'):
        await run_json_stage(invoke, lambda value: value, stage='quiz')
    assert invoke.await_count == 1


@pytest.mark.asyncio
async def test_transient_failure_json_repair_and_timeout_share_three_attempts(monkeypatch):
    monkeypatch.setattr('app.llm.structured_stage.asyncio.sleep', AsyncMock())
    request = httpx.Request('POST', 'https://provider.invalid')
    error = APIStatusError('private diagnostics', response=httpx.Response(503, request=request), body=None)
    invoke = AsyncMock(side_effect=[error, message('broken json'), APITimeoutError(request=request)])
    with pytest.raises(StructuredGenerationError, match='^provider_failed$'):
        await run_json_stage(invoke, lambda value: value, stage='report')
    assert invoke.await_count == 3


@pytest.mark.asyncio
async def test_cached_response_survives_revalidation_without_new_call():
    context = SimpleNamespace(checkpoints={'quiz': {'output': [{'content': '{"ok":true}', 'finish_reason': 'stop'}]}}, external=AsyncMock())
    invoke = AsyncMock()
    assert await run_json_stage(invoke, lambda value: value, stage='quiz', context=context) == {'ok': True}
    context.external.assert_not_called()
    invoke.assert_not_called()


@pytest.mark.asyncio
async def test_provider_configuration_failure_is_not_counted_as_a_network_attempt():
    context = SimpleNamespace(checkpoints={}, external=AsyncMock())
    def prepare():
        raise ValueError('Missing provider configuration')
    with pytest.raises(ValueError, match='Missing provider configuration'):
        await run_json_stage(AsyncMock(), lambda value: value, stage='report', context=context, prepare=prepare)
    context.external.assert_not_called()
