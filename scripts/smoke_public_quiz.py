"""One opt-in public-topic job: at most one basic search and three generation attempts."""
import argparse
import asyncio
import json
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]


async def main(web):
    identity = json.loads((ROOT / '.local/text-quiz-browser.json').read_text(encoding='utf8'))['account']
    evidence = {'recorded_at': datetime.now(timezone.utc).isoformat(), 'data_source': 'Public Python list/dictionary topic',
                    'web_search': web, 'max_external_calls': 4 if web else 3, 'currency_cost': None,
                    'limitations': ['Integration smoke, not question correctness evaluation', 'No currency billing returned', 'Web references are not verified per-question citations']}
    task_id, last = None, None
    async with httpx.AsyncClient(base_url='http://127.0.0.1:18081/api/v1/', timeout=25,
                                 headers={'Authorization': 'Bearer ' + identity['token']}) as client:
        async def api(method, endpoint, data=None, key=None):
            response = await client.request(method, endpoint, json=data, headers={'Idempotency-Key': key} if key else None)
            if response.status_code != 200:
                raise RuntimeError(f'{endpoint.split("/")[0]} returned HTTP {response.status_code}')
            return response.json()['data']
        started = time.monotonic()
        try:
            payload = {'user_input': 'Python 列表与字典：索引、可变性与键的基本用法', 'question_count': 3,
                           'question_counts': {'single': 1, 'multiple': 1, 'judge': 1}, 'use_web_search': web}
            key = uuid.uuid4().hex
            created = await api('POST', 'quiz/generate/async', payload, key)
            task_id = created['task_id']
            duplicate = await api('POST', 'quiz/generate/async', payload, key)
            assert duplicate['task_id'] == task_id
            for _ in range(100):
                last = await api('GET', 'learning/tasks/' + task_id)
                if last['status'] == 'completed':
                    break
                if last['status'] in ('failed', 'cancelled'):
                    raise RuntimeError('Public task failed: ' + str(last.get('error_code')))
                await asyncio.sleep(1)
            else:
                raise RuntimeError('Smoke wait budget exceeded')
            detail = await api('GET', 'user/quizzes/' + last['result']['quiz_id'])
            assert sorted(q['type'] for q in detail['questions']) == ['judge', 'multiple', 'single']
            assert all(not {'answer', 'explanation', 'citations'} & q.keys() for q in detail['questions'])
            assert detail['source_context']['source_type'] == ('public_web' if web else 'model_knowledge')
            assert not detail['source_context']['sources']
            assert last['trace']['model_calls'] <= evidence['max_external_calls']
            (ROOT / '.local/public-quiz-browser.json').write_text(json.dumps({'account': identity, 'taskId': task_id, 'quizId': detail['quiz_id']}, ensure_ascii=False), encoding='utf8')
            evidence.update(status='passed', checks=['paid_generation', 'same_key_single_job', 'exact_three_type_counts', 'answer_hiding', 'provenance_persisted'])
        except Exception as error:
            evidence.update(status='failed', failure_type=type(error).__name__, diagnostic=str(error)[:160])
            raise
        finally:
            if task_id and (not last or last['status'] not in ('completed', 'failed', 'cancelled')):
                await api('POST', 'learning/tasks/' + task_id + '/cancel')
            evidence.update(elapsed_ms=round((time.monotonic()-started)*1000), trace=last.get('trace') if last else None)
            (ROOT / 'docs/evidence/public-quiz-live.json').write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    print(json.dumps({'status': evidence['status'], 'external_calls': last['trace']['model_calls'], 'reported_tokens': last['trace']['tokens']}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--paid', action='store_true')
    parser.add_argument('--web', action='store_true')
    args = parser.parse_args()
    if not args.paid:
        parser.error('--paid is required; this script consumes a bounded provider budget')
    asyncio.run(main(args.web))
