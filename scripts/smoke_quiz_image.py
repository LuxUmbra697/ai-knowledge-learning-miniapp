"""Opt-in: one public question and one private illustration, no retries of the smoke itself."""
import argparse
import asyncio
import io
import json
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import httpx
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]


async def main():
    identity = json.loads((ROOT / '.local/text-quiz-browser.json').read_text(encoding='utf8'))['account']
    evidence = {'recorded_at': datetime.now(timezone.utc).isoformat(), 'data_source': 'Public plant biology topic; no private document',
                'max_text_calls': 3, 'max_image_calls': 1, 'currency_cost': None, 'checks': [],
                'limitations': ['Integration smoke, not scientific image correctness evaluation', 'Currency billing unavailable', 'No native device verification']}
    tasks, image_task, last = [], None, None
    started = time.monotonic()
    async with httpx.AsyncClient(base_url='http://127.0.0.1:18081/api/v1/', timeout=25,
                                 headers={'Authorization': 'Bearer ' + identity['token']}, trust_env=False) as client:
        async def api(method, path, data=None, key=None):
            response = await client.request(method, path, json=data, headers={'Idempotency-Key': key} if key else None)
            if response.status_code != 200:
                raise RuntimeError(f'{path.split("/")[0]} HTTP {response.status_code}')
            return response.json()['data']
        async def wait(task_id):
            for _ in range(175):
                task = await api('GET', 'learning/tasks/' + task_id)
                if task['status'] in ('completed', 'failed', 'cancelled'):
                    return task
                await asyncio.sleep(1)
            raise RuntimeError('Task wait budget exceeded')
        try:
            created = await api('POST', 'quiz/generate/async', {'user_input': '植物的叶片通过气孔进行气体交换：只出一道基础单选题。',
                                'question_count': 1, 'question_counts': {'single': 1}, 'generate_images': True}, uuid.uuid4().hex)
            tasks.append(created['task_id'])
            last = await wait(tasks[0])
            evidence['text_trace'] = last['trace']
            assert last['status'] == 'completed', 'Text generation failed'
            detail = await api('GET', 'user/quizzes/' + last['result']['quiz_id'])
            question = detail['questions'][0]
            assert len(detail['questions']) == 1 and question['image_asset_id'] and 'answer' not in question
            evidence['checks'].append('text_committed_with_hidden_answer_and_owned_asset')
            asset = await api('GET', 'quiz/images/' + question['image_asset_id'])
            tasks.append(asset['task_id'])
            image_task = await wait(asset['task_id'])
            evidence['image_trace'] = image_task['trace']
            assert image_task['status'] == 'completed' and image_task['result']['image_count'] == 1, 'Image generation or private storage failed'
            asset = await api('GET', 'quiz/images/' + question['image_asset_id'])
            assert asset['status'] == 'locked' and asset['url'] is None
            await api('POST', 'quiz/' + detail['quiz_id'] + '/answer', {'question_id': question['id'], 'selected_answers': ['A'], 'duration_ms': 1000})
            evidence['checks'].append('image_hidden_until_server_scored_submission')
            asset = await api('GET', 'quiz/images/' + question['image_asset_id'])
            assert asset['status'] == 'ready' and asset['expires_in'] == 120
            async with httpx.AsyncClient(timeout=15, trust_env=False, follow_redirects=False) as reader:
                signed = await reader.get(asset['url'])
                assert signed.status_code == 200 and signed.headers['content-type'].startswith('image/jpeg')
                assert len(signed.content) <= 350000
                with Image.open(io.BytesIO(signed.content)) as image:
                    assert max(image.size) <= 640
                    evidence['image'] = {'width': image.width, 'height': image.height, 'size_bytes': len(signed.content)}
                parts = urlsplit(asset['url'])
                unsigned = await reader.get(urlunsplit((parts.scheme, parts.netloc, parts.path, '', '')))
                assert unsigned.status_code == 403
                outsider = await reader.post('http://127.0.0.1:18081/api/v1/user/account/register', json={
                    'username': 'e2e_image_' + uuid.uuid4().hex[:12], 'password': 'Local-E2E-Only-1976', 'nickname': '配图隔离验收'})
                assert outsider.status_code == 200
                denied = await reader.get('http://127.0.0.1:18081/api/v1/quiz/images/' + question['image_asset_id'],
                                          headers={'Authorization': 'Bearer ' + outsider.json()['data']['token']})
                assert denied.status_code == 404
            assert last['trace']['model_calls'] <= 3 and image_task['trace']['model_calls'] == 1
            evidence['checks'] += ['separate_durable_image_job', 'one_paid_image_call', 'private_signed_jpeg_200', 'unsigned_object_403', 'other_user_404', 'bounded_pixel_and_byte_dimensions']
            evidence['status'] = 'passed'
            (ROOT / '.local/image-quiz-browser.json').write_text(json.dumps({'account': identity, 'quizId': detail['quiz_id'],
                                                                          'assetId': question['image_asset_id'], 'taskId': asset['task_id']}, ensure_ascii=False), encoding='utf8')
        except Exception as error:
            diagnostic = str(error)[:160] if isinstance(error, (AssertionError, RuntimeError)) else type(error).__name__
            evidence.update(status='failed', failure_type=type(error).__name__, diagnostic=diagnostic)
            raise
        finally:
            for task_id in tasks:
                await api('POST', 'learning/tasks/' + task_id + '/cancel')
            evidence['elapsed_ms'] = round((time.monotonic() - started) * 1000)
            (ROOT / 'docs/evidence/quiz-image-live.json').write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    print(json.dumps({'status': evidence['status'], 'text_calls': last['trace']['model_calls'], 'image_calls': image_task['trace']['model_calls'], 'image': evidence['image']}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--paid', action='store_true')
    if not parser.parse_args().paid:
        parser.error('--paid is required; this command consumes a bounded paid budget')
    asyncio.run(main())
