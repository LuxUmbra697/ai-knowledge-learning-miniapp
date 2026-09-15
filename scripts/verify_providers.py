"""Explicit smoke run: exactly one tiny chat request and one two-text embedding batch."""
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))

from openai import OpenAI, APIStatusError, APITimeoutError, APIConnectionError
from app.core.config import get_settings


def main():
    if sys.argv[1:] != ['--confirm-two-small-requests']:
        raise SystemExit('Pass --confirm-two-small-requests to permit these two external calls')
    settings = get_settings()
    results = {'data_origin': 'synthetic public phrases; no user documents', 'max_calls': 2,
               'currency_cost': None, 'cost_note': 'Token counts are measured; billed currency is not queried.'}
    for name, key, base, model in [
        ('chat', settings.deepseek_api_key, settings.deepseek_base_url, settings.deepseek_model),
        ('embedding', settings.dashscope_api_key, settings.dashscope_base_url, settings.dashscope_embedding_model),
    ]:
        if not key:
            results[name] = {'status': 'not_configured'}
            continue
        start = time.monotonic()
        try:
            with OpenAI(api_key=key, base_url=base, timeout=25, max_retries=0) as client:
                if name == 'chat':
                    response = client.chat.completions.create(model=model, messages=[{'role': 'user', 'content': 'Reply with the single word OK.'}], max_tokens=8, temperature=0)
                    assert response.choices[0].message.content.strip().strip('.') == 'OK'
                    result = {'status': 'passed', 'usage': response.usage.model_dump()}
                else:
                    response = client.embeddings.create(model=model, input=['栈遵循后进先出原则。', '队列遵循先进先出原则。'], encoding_format='float')
                    assert len(response.data) == 2 and len(response.data[0].embedding) > 0
                    result = {'status': 'passed', 'dimensions': len(response.data[0].embedding), 'usage': response.usage.model_dump()}
        except APIStatusError as error:
            status = error.status_code
            result = {'status': {401: 'authentication_failed', 403: 'permission_or_region_denied', 429: 'quota_or_rate_limit'}.get(status, 'provider_http_error'), 'http_status': status}
        except APITimeoutError:
            result = {'status': 'timeout'}
        except APIConnectionError:
            result = {'status': 'connection_failed'}
        except (AssertionError, ValueError, TypeError, AttributeError):
            result = {'status': 'invalid_response'}
        result.update(model=model, calls=1, latency_ms=round((time.monotonic() - start) * 1000))
        results[name] = result
    results['measured_at_utc'] = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
    (ROOT / 'docs/evidence/provider-smoke.json').write_text(json.dumps(results, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(results))


if __name__ == '__main__':
    main()
