"""Three explicit paid conversations, at most nine text calls; only synthetic preferences."""
import argparse
import asyncio
import json
import secrets
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]


async def main(base_url):
    evidence = {'recorded_at': datetime.now(timezone.utc).isoformat(), 'fixture': 'Synthetic learning preferences, two canonical adult fictional characters',
                'maximum_text_calls': 9, 'tasks': [], 'currency_cost': None, 'status': 'running'}
    directory = ROOT / '.local/sdlc/companion'
    directory.mkdir(parents=True, exist_ok=True)
    task_ids = []
    async with httpx.AsyncClient(base_url=base_url, timeout=25, trust_env=False) as client:
        async def api(method, endpoint, data=None, key=None):
            response = await client.request(method, endpoint, json=data, headers={'Idempotency-Key': key} if key else None)
            if response.status_code != 200:
                raise RuntimeError(f'Companion API returned HTTP {response.status_code}')
            return response.json()['data']

        username, password = 'buddy_' + uuid.uuid4().hex[:16], secrets.token_urlsafe(24)
        account = await api('POST', 'user/account/register', {'username': username, 'password': password, 'nickname': '伙伴联调同学'})
        client.headers['Authorization'] = 'Bearer ' + account['token']
        (ROOT / '.local/companion-browser.json').write_text(json.dumps({'account': account, 'username': username, 'password': password}, ensure_ascii=False), encoding='utf8')

        async def turn(identity, message):
            before = await api('GET', 'companions/' + identity)
            command = {'version': before['version'], 'message': message}
            key = uuid.uuid4().hex
            task = await api('POST', f'companions/{identity}/turns', command, key)
            task_ids.append(task['task_id'])
            assert (await api('POST', f'companions/{identity}/turns', command, key))['task_id'] == task['task_id']
            started = time.monotonic()
            for _ in range(180):
                task = await api('GET', 'learning/tasks/' + task['task_id'])
                if task['status'] in ('completed', 'failed', 'cancelled'):
                    break
                await asyncio.sleep(1)
            evidence['tasks'].append({'character': identity, 'status': task['status'], 'elapsed_ms': round((time.monotonic() - started) * 1000), 'trace': task['trace']})
            assert task['status'] == 'completed', 'Dialogue task did not complete'
            result = await api('GET', 'companions/' + identity)
            reply = result['turns'][-1]['response']
            assert reply['used_memory_ids'], 'No confirmed preference was referenced'
            assert result['turn_count'] == before['turn_count'] + 1
            return result

        try:
            await api('PUT', 'companions/pink/memories', {'version': 0, 'items': [
                {'id': 'study', 'kind': 'study', 'text': '喜欢先看例子再读定义'}, {'id': 'name', 'kind': 'name', 'text': '小禾'}]})
            first = await turn('pink', '小满，你还记得我希望怎么学习吗？今天有一点累，想先聊聊。')
            assert '例子' in first['turns'][-1]['response']['dialogue']
            second = await turn('pink', '谢谢你记住了。我们继续按我的学习偏好慢慢来吧，也别忘记休息。')
            assert len(second['turns']) == 2
            assert (await api('GET', 'companions/orange'))['memories'] == []
            await api('PUT', 'companions/orange/memories', {'version': 0, 'items': [{'id': 'support', 'kind': 'support', 'text': '喜欢简短具体的提醒'}]})
            third = await turn('orange', '澄，按我喜欢的相处方式陪我整理一下今天吧。我尊重你的边界，也愿意一起认真核对记录。')
            assert third['turns'][0]['response']['used_memory_ids'] == ['support']
            assert first['character']['primary'] != third['character']['primary']
            assert all(item['trace']['model_calls'] <= 3 for item in evidence['tasks'])
            evidence.update(status='passed', checks=['two_distinct_personas', 'two_persistent_pink_turns', 'confirmed_preference_recall', 'isolated_orange_memory', 'paid_job_idempotency', 'structured_emotion_and_action'],
                            limitations=['Three controlled integration turns, not a general personality consistency benchmark', 'No native-device or production verification in this run'])
        except Exception as error:
            evidence.update(status='failed', error_type=type(error).__name__)
            raise
        finally:
            for task_id in task_ids:
                await api('POST', 'learning/tasks/' + task_id + '/cancel')
            evidence['external_calls'] = sum(item['trace']['model_calls'] for item in evidence['tasks'])
            evidence['reported_tokens'] = sum(item['trace']['tokens'] for item in evidence['tasks'])
            (directory / 'live-evidence.json').write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    print(json.dumps({key: evidence[key] for key in ('status', 'external_calls', 'reported_tokens')}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--paid', action='store_true')
    parser.add_argument('--base-url', choices=['http://127.0.0.1:18081/api/v1/', 'https://lux-umbra.xyz/ai-learn/api/v1/'], default='http://127.0.0.1:18081/api/v1/')
    args = parser.parse_args()
    if not args.paid:
        parser.error('--paid required: three turns, maximum nine text calls')
    asyncio.run(main(args.base_url))
