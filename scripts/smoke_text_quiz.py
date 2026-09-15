"""Opt-in paid five-type generation and written grading on a verified public fixture only."""
import argparse
import asyncio
import json
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import httpx

from run_local import configure

ROOT = Path(__file__).resolve().parents[1]


async def main():
    configure(True)
    from app.core.db import close_mysql_pool, connect_mysql
    from app.repositories import quiz_repository
    source = json.loads((ROOT / '.local/m2-browser.json').read_text(encoding='utf8'))
    public_source = (ROOT / 'evaluation/fixtures/learning-rate.md').read_text(encoding='utf8')
    traces = []
    evidence = {'recorded_at': datetime.now(timezone.utc).isoformat(), 'data_source': 'Public synthetic learning-rate fixture',
                'purpose': 'Integration smoke with generated reference answer, not a human grading accuracy evaluation',
                'max_external_calls': 7, 'currency_cost': None, 'cost_note': 'Provider billing was not returned; token/call counts are reported instead.'}
    async with httpx.AsyncClient(base_url='http://127.0.0.1:18081/api/v1/', timeout=25,
                                 headers={'Authorization': 'Bearer ' + source['account']['token']}) as client:
        async def api(method, endpoint, data=None, key=None):
            response = await client.request(method, endpoint, json=data, headers={'Idempotency-Key': key} if key else None)
            if response.status_code != 200:
                raise RuntimeError(f'{endpoint.split("/")[0]} returned HTTP {response.status_code}')
            return response.json()['data']
        async def settle(created):
            started = time.monotonic()
            for _ in range(100):
                task = await api('GET', 'learning/tasks/' + created['task_id'])
                if task['status'] == 'completed':
                    traces.append({'kind': task['kind'], 'elapsed_ms': round((time.monotonic()-started)*1000), 'trace': task['trace']})
                    return task['result']
                if task['status'] in ('failed', 'cancelled'):
                    raise RuntimeError(f"{task['kind']} task failed: {task.get('error_code')}")
                await asyncio.sleep(1)
            raise RuntimeError('Task wait exceeded the smoke budget')
        try:
            chunks = await api('GET', f"knowledge/documents/{source['doc_id']}/chunks")
            if not chunks['items'] or chunks['total'] != len(chunks['items']) or any(row['doc_id'] != source['doc_id'] or row['content'] not in public_source for row in chunks['items']):
                raise RuntimeError('Fixture preflight failed; no private content may be exported by this smoke')
            quota = dict(single=1, multiple=1, judge=1, fill=1, written=1)
            created = await api('POST', 'quiz/generate/async', dict(user_input='根据学习率讲义生成五种题型练习', doc_id=source['doc_id'], question_count=5, question_counts=quota, generate_images=False), uuid.uuid4().hex)
            result = await settle(created)
            quiz_id = result['quiz_id']
            visible = await api('GET', 'user/quizzes/' + quiz_id)
            assert sorted(q['type'] for q in visible['questions']) == sorted(quota)
            assert all(not {'answer', 'explanation', 'rubric', 'accepted_answers', 'citations'} & q.keys() for q in visible['questions'])
            await connect_mysql()
            try:
                stored = await quiz_repository.get_quiz_detail(quiz_id, source['account']['user']['id'])
            finally:
                await close_mysql_pool()
            for question in stored['questions']:
                submission = dict(question_id=question['id'], selected_answers=question['answer'], duration_ms=1000)
                endpoint = f'quiz/{quiz_id}/answer' + ('/async' if question['type'] == 'written' else '')
                answer = await api('POST', endpoint, submission, uuid.uuid4().hex)
                if question['type'] == 'written':
                    await settle(answer)
                else:
                    assert answer['record']['is_correct']
            detail = await api('GET', 'user/quizzes/' + quiz_id)
            assert len(detail['answer_records']) == 5
            assert all(record['is_correct'] for record in detail['answer_records'])
            assert next(record for record in detail['answer_records'] if 'grading' in record and record['grading']['method'] == 'model-rubric-v1')['grading']['criteria']
            (ROOT / '.local/text-quiz-browser.json').write_text(json.dumps({'account': source['account'], 'quizId': quiz_id, 'taskId': created['task_id']}, ensure_ascii=False), encoding='utf8')
            evidence.update(status='passed', checks=['exact_five_type_distribution', 'answer_rubric_hiding', 'four_authoritative_objective_answers', 'one_real_model_rubric_assessment', 'five_persisted_attempts'])
        except Exception as error:
            evidence.update(status='failed', failure_type=type(error).__name__, diagnostic=str(error)[:160])
            raise
        finally:
            evidence['tasks'] = traces
            evidence['external_calls'] = sum(row['trace']['model_calls'] for row in traces)
            evidence['reported_tokens'] = sum(row['trace']['tokens'] for row in traces)
            (ROOT / 'docs/evidence/text-quiz-live.json').write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    print(json.dumps({key: evidence[key] for key in ('status', 'external_calls', 'reported_tokens')}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--paid', action='store_true', help='Explicitly allow at most one embedding, three quiz and three rubric calls')
    args = parser.parse_args()
    if not args.paid:
        parser.error('--paid is required; this script consumes a bounded provider budget')
    asyncio.run(main())
