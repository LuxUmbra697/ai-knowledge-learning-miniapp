"""Bounded JSON repair with resumable provider responses and no hidden SDK retries."""
import asyncio
import json
import re
import time

import structlog
from openai import APIConnectionError, APIStatusError
from pydantic import ValidationError

logger = structlog.get_logger()


class StructuredGenerationError(RuntimeError):
    def __init__(self, message, failure_code=None):
        super().__init__(message)
        self.failure_code = failure_code or message


def provider_failure(error, allow_rate_retry):
    status = getattr(error, 'status_code', None)
    body = getattr(error, 'body', None)
    detail = body.get('error', body) if isinstance(body, dict) else {}
    code = str(detail.get('code', '')).lower() if isinstance(detail, dict) else ''
    limited = status == 429 and code in {'rate_limit_exceeded', 'rate_limit_error', 'requests_limit_exceeded'}
    retryable = status is None or status >= 500 or (allow_rate_retry and limited)
    reason = ('provider_auth' if status in (401, 403) else 'provider_quota' if status in (402, 429) and not limited
              else 'provider_parameter' if status in (400, 404, 422) else 'provider_unavailable')
    try:
        delay = min(8, max(.5, float(error.response.headers.get('retry-after', 1))))
    except (AttributeError, ValueError, TypeError):
        delay = 1
    return {'error_type': type(error).__name__, 'retryable': retryable, 'failure_code': reason, 'retry_after': delay}


def parse_json(content):
    if not isinstance(content, str) or not content.strip() or len(content) > 96000:
        raise ValueError('Expected a nonempty bounded JSON response')
    fenced = re.fullmatch(r'```(?:json)?\s*(.*?)\s*```', content.strip(), re.DOTALL)
    return json.loads(fenced.group(1) if fenced else content.strip())


async def run_json_stage(invoke, validate, *, stage, context=None, input_bytes=lambda _feedback: 0, prepare=None, max_attempts=3):
    if not 1 <= max_attempts <= 10:
        raise ValueError('Stage attempts must be between one and ten')
    history = context.checkpoints.get(stage, {}).get('output', []) if context else []
    feedback = ''
    for attempt in range(max_attempts):
        if attempt >= len(history):
            if prepare:
                prepare()
            async def call():
                started = time.monotonic()
                logger.info('structured_call_started', stage=stage, attempt=attempt + 1, input_bytes=input_bytes(feedback))
                try:
                    response = await invoke(feedback)
                    usage = getattr(response, 'usage_metadata', None)
                    metadata = getattr(response, 'response_metadata', None)
                    tokens = usage.get('total_tokens') if isinstance(usage, dict) else None
                    item = {'content': response.content, 'finish_reason': metadata.get('finish_reason') if isinstance(metadata, dict) else None}
                except (APIConnectionError, APIStatusError) as error:
                    item = provider_failure(error, max_attempts > 3)
                    tokens = None
                logger.info('structured_call_finished', stage=stage, attempt=attempt + 1,
                            elapsed_ms=round((time.monotonic() - started) * 1000), tokens=tokens,
                            error_type=item.get('error_type'), finish_reason=item.get('finish_reason'))
                return [*history, item], tokens
            if context:
                history = await context.external(stage, call, input_bytes(feedback))
            else:
                history, _tokens = await call()
        item = history[attempt]
        if item.get('error_type'):
            if not item['retryable'] or attempt == max_attempts - 1:
                raise StructuredGenerationError('provider_failed', item.get('failure_code', 'provider_unavailable'))
            await asyncio.sleep(min(8, max(item.get('retry_after', 0), .5 * (attempt + 1))))
            continue
        try:
            if item.get('finish_reason') == 'length':
                raise ValueError('Response was truncated; shorten the output while retaining every required field')
            return validate(parse_json(item['content']))
        except (ValueError, TypeError) as error:
            diagnostic = json.dumps(error.errors(include_input=False, include_context=False), ensure_ascii=False) if isinstance(error, ValidationError) else str(error)
            feedback = '上次输出未通过校验：' + diagnostic[:700] + '。请修复并重新输出完整 JSON，不要输出思维过程。'
            if attempt + 1 < max_attempts:
                await asyncio.sleep(min(3, .5 * (attempt + 1)))
    raise StructuredGenerationError('validation_failed_after_three_attempts' if max_attempts == 3 else f'validation_failed_after_{max_attempts}_attempts', 'validation_failed')
