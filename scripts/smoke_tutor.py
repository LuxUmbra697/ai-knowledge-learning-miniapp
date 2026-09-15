"""Opt-in two-turn tutoring plus one diagnosis on verified public/synthetic materials."""
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
    from app.core.config import get_settings
    from app.core.db import close_mysql_pool, connect_mysql
    from app.repositories.quiz_repository import save_quiz_session
    from app.services.grading_service import AnswerSubmission, submit_question
    from app.services.tutor_service import question_context
    settings = get_settings()
    assert (settings.mysql_host, settings.mysql_port, settings.mysql_database) == ('127.0.0.1', 23308, 'ai_learn_local')
    fixture = json.loads((ROOT / '.local/m2-browser.json').read_text(encoding='utf8'))
    source = (ROOT / 'evaluation/fixtures/learning-rate.md').read_text(encoding='utf8')
    identity = fixture['account']
    evidence = {'recorded_at': datetime.now(timezone.utc).isoformat(), 'data_source': 'Verified public learning-rate fixture and one explicitly synthetic wrong answer',
                'max_external_calls': 11, 'currency_cost': None, 'tasks': [],
                'limitations': ['Integration and source/schema checks, not measured student learning outcomes', 'Diagnosis is a tentative model suggestion', 'No automated semantic guarantee against a too-direct hint']}
    task_ids = []
    async with httpx.AsyncClient(base_url='http://127.0.0.1:18081/api/v1/', timeout=25, trust_env=False,
                                 headers={'Authorization': 'Bearer ' + identity['token']}) as client:
        async def api(method, endpoint, data=None, key=None):
            response = await client.request(method, endpoint, json=data, headers={'Idempotency-Key': key} if key else None)
            if response.status_code != 200:
                raise RuntimeError(f'{endpoint.split("/")[0]} HTTP {response.status_code}')
            return response.json()['data']
        async def turn(session_id, version, message):
            key = uuid.uuid4().hex
            body = {'version': version, 'message': message}
            task = await api('POST', f'learning/tutor/sessions/{session_id}/turns', body, key)
            task_ids.append(task['task_id'])
            assert (await api('POST', f'learning/tutor/sessions/{session_id}/turns', body, key))['task_id'] == task['task_id']
            started = time.monotonic()
            for _ in range(175):
                task = await api('GET', 'learning/tasks/' + task['task_id'])
                if task['status'] in ('completed', 'failed', 'cancelled'):
                    break
                await asyncio.sleep(1)
            evidence['tasks'].append({'mode': 'socratic' if version < 2 else 'diagnosis', 'elapsed_ms': round((time.monotonic()-started)*1000), 'trace': task['trace'], 'status': task['status']})
            assert task['status'] == 'completed', 'Tutor did not complete'
            detail = await api('GET', 'learning/tutor/sessions/' + session_id)
            answer = detail['turns'][-1]['response']
            assert answer['question'].count('?') + answer['question'].count('？') == 1
            for citation in answer['citations']:
                assert any(item['id'] == citation['evidence_id'] and citation['quote'] in item['content'] for item in answer['evidence'])
            return detail
        try:
            chunks = await api('GET', f"knowledge/documents/{fixture['doc_id']}/chunks")
            if not chunks['items'] or chunks['total'] != len(chunks['items']) or any(item['doc_id'] != fixture['doc_id'] or item['content'] not in source for item in chunks['items']):
                raise RuntimeError('Public fixture preflight failed; no private content may be exported')
            session = await api('POST', 'learning/tutor/sessions', {'goal': '理解学习率过大为什么会发生震荡', 'doc_ids': [fixture['doc_id']], 'mode': 'socratic'}, uuid.uuid4().hex)
            first = await turn(session['session_id'], 0, '请先用一个提示引导我理解，不直接给出完整答案。')
            assert first['turns'][0]['response']['status'] == 'hint' and len(first['turns'][0]['response']['hint']) <= 180
            second = await turn(session['session_id'], 1, '我猜是每一步走得太远，跨过了最低点，但不知道怎样解释。')
            assert second['version'] == 2 and second['turns'][1]['response']['memory_turns'] == 1
            await connect_mysql()
            try:
                quiz_id = 'quiz_smoke_' + uuid.uuid4().hex
                questions = [{'id': 'q1', 'type': 'single', 'stem': '学习率过大时，参数更新可能出现什么现象？',
                              'options': [{'key': 'A', 'text': '跨过低点并震荡'}, {'key': 'B', 'text': '必然平稳到达最优点'}],
                              'answer': ['A'], 'explanation': '步长过大可能跨过低点并在两侧震荡；并非必然平稳收敛。此题为合成联调题。',
                              'knowledge_point': '学习率与震荡', 'difficulty': 'easy'}]
                await save_quiz_session(quiz_id, identity['user']['id'], '合成错题诊断联调', 'Synthetic integration fixture', 'Public learning-rate concept', questions)
                await submit_question(quiz_id, identity['user']['id'], AnswerSubmission(question_id='q1', selected_answers=['B'], duration_ms=1000))
                target = await question_context(identity['user']['id'], quiz_id, 'q1')
            finally:
                await close_mysql_pool()
            diagnosis = await api('POST', 'learning/tutor/sessions', {'goal': '找出本次作答与参考解析的差异', 'mode': 'diagnosis', 'card_id': target['card_id']}, uuid.uuid4().hex)
            diagnosed = await turn(diagnosis['session_id'], 0, '我把步长更大理解成一定收敛更快，请帮助我检查。')
            evidence['tasks'][-1]['mode'] = 'diagnosis'
            result = diagnosed['turns'][0]['response']
            assert result['status'] == 'diagnosis' and result['diagnosis_source'] == 'model_suggestion_requires_confirmation'
            assert any(item['source_type'] == 'stored_practice' for item in result['evidence'])
            assert all(not item['response']['practice'] or not item['response']['practice']['created'] for item in [*second['turns'], *diagnosed['turns']])
            (ROOT / '.local/tutor-browser.json').write_text(json.dumps({'account': identity, 'sessionId': session['session_id'], 'diagnosisId': diagnosis['session_id'], 'cardId': target['card_id']}, ensure_ascii=False), encoding='utf8')
            evidence.update(status='passed', checks=['two_paid_socratic_turns', 'single_guiding_question', 'exact_quotes', 'bounded_prior_turn_memory', 'idempotent_admission', 'owned_persisted_wrong_answer', 'tentative_diagnosis', 'no_automatic_practice_or_plan_mutation'])
        except Exception as error:
            evidence.update(status='failed', failure_type=type(error).__name__, diagnostic=str(error)[:160] if isinstance(error, (AssertionError, RuntimeError)) else type(error).__name__)
            raise
        finally:
            for task_id in task_ids:
                await api('POST', 'learning/tasks/' + task_id + '/cancel')
            evidence['external_calls'] = sum(item['trace']['model_calls'] for item in evidence['tasks'])
            evidence['reported_tokens'] = sum(item['trace']['tokens'] for item in evidence['tasks'])
            (ROOT / 'docs/evidence/tutor-live.json').write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    print(json.dumps({key: evidence[key] for key in ('status', 'external_calls', 'reported_tokens')}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--paid', action='store_true')
    if not parser.parse_args().paid:
        parser.error('--paid is required; maximum 11 external calls for three tutor turns')
    asyncio.run(main())
