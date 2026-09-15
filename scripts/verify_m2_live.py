"""Opt-in loopback upload/index/citation verification: at most four embedding requests."""
import argparse
import asyncio
from datetime import datetime, timezone
import json
from pathlib import Path
import secrets
import time
import uuid

import httpx

ROOT = Path(__file__).resolve().parents[1]
MATERIAL = '''# 梯度下降学习笔记
## 参数更新
梯度下降沿损失函数的负梯度方向更新模型参数。更新公式为：新参数 = 旧参数 - 学习率 × 梯度。
梯度描述函数在当前位置增长最快的方向，负梯度对应局部下降方向。
## 学习率
学习率控制每次参数更新的步长。学习率过大可能发生震荡，学习率过小通常导致收敛缓慢。
## 学习边界
本讲义只讨论优化方法，不包含医学诊断、用户密码或最新天气信息。
'''


async def main(evidence_name='m2-live-index'):
    checks = []
    async with httpx.AsyncClient(base_url='http://127.0.0.1:18081/api/v1', timeout=65) as client:
        accounts = []
        for _ in range(2):
            username = 'm2_' + uuid.uuid4().hex[:12]
            password = secrets.token_urlsafe(24)
            response = await client.post('/user/account/register', json={'username': username, 'password': password, 'nickname': '证据学习测试'})
            response.raise_for_status()
            accounts.append({**response.json()['data'], 'username': username, 'password': password})
        headers = {'Authorization': 'Bearer ' + accounts[0]['token']}
        other = {'Authorization': 'Bearer ' + accounts[1]['token']}

        async def upload(filename, content):
            response = await client.post('/knowledge/documents', headers=headers, files={'file': (filename, content.encode(), 'text/markdown')})
            response.raise_for_status()
            assert response.json()['code'] == 0
            return response.json()['data']

        async def ready(doc_id):
            for _ in range(35):
                response = await client.get(f'/knowledge/documents/{doc_id}', headers=headers)
                response.raise_for_status()
                data = response.json()['data']
                if data['status'] != 'processing':
                    assert data['status'] == 'ready', data.get('error_message')
                    return data
                await asyncio.sleep(1)
            raise AssertionError('Index did not finish within 35 seconds')

        started = time.perf_counter()
        first = await upload('梯度下降学习笔记.md', MATERIAL)
        status = await ready(first['doc_id'])
        assert status['chunk_count'] >= 3 and status['revision'] == 1
        checks.append('markdown_parsing_embedding_index_ready')
        duplicate = await upload('重命名副本.md', MATERIAL)
        assert duplicate['duplicate'] and duplicate['doc_id'] == first['doc_id']
        checks.append('duplicate_reuses_document_without_embedding')

        second = await upload('学习率补充讲义.md', '# 优化补充\n学习率决定一次参数更新的步长。设置过大会导致震荡，设置过小会使收敛变慢。\n这是公开可复现的合成教学样例，不含用户私人材料。')
        await ready(second['doc_id'])
        query = {'query': '学习率过大会怎样？', 'doc_ids': [first['doc_id'], second['doc_id']]}
        response = await client.post('/knowledge/retrieve', headers=headers, json=query)
        response.raise_for_status()
        retrieval = response.json()['data']
        assert retrieval['status'] == 'ok' and retrieval['evidence']
        assert retrieval['trace']['reranker'] == 'lexical'
        evidence = retrieval['evidence'][0]
        citation_url = f'/knowledge/documents/{evidence["doc_id"]}/chunks/{evidence["chunk_id"]}?revision=1'
        response = await client.get(citation_url, headers=headers)
        assert response.status_code == 200 and response.json()['data']['content'] == evidence['content']
        checks.append('hybrid_rerank_and_exact_citation_round_trip')
        for method, url, body in [('GET', citation_url, None), ('GET', f'/knowledge/documents/{first["doc_id"]}', None),
                                 ('POST', '/knowledge/retrieve', query), ('DELETE', f'/knowledge/documents/{first["doc_id"]}', None)]:
            denied = await client.request(method, url, headers=other, json=body)
            assert denied.status_code == 404
        assert (await client.post('/knowledge/retrieve', headers=headers, json={**query, 'user_id': accounts[1]['user']['id']})).status_code == 422
        checks.append('cross_user_document_citation_retrieve_delete_blocked')

        response = await client.post(f'/knowledge/documents/{first["doc_id"]}/reindex', headers=headers)
        response.raise_for_status()
        assert (await ready(first['doc_id']))['revision'] == 2
        first_evidence = next(item for item in retrieval['evidence'] if item['doc_id'] == first['doc_id'])
        stale_url = f'/knowledge/documents/{first["doc_id"]}/chunks/{first_evidence["chunk_id"]}?revision=1'
        assert (await client.get(stale_url, headers=headers)).status_code == 404
        checks.append('reindex_invalidates_previous_revision_citations')
        assert (await client.delete(f'/knowledge/documents/{first["doc_id"]}', headers=headers)).status_code == 200
        denied = await client.post('/knowledge/retrieve', headers=headers, json={'query': '梯度下降', 'doc_ids': [first['doc_id']]})
        assert denied.status_code == 404
        checks.append('deleted_document_rejected_before_retrieval')

        response = await client.get('/learning/tasks', headers=headers)
        response.raise_for_status()
        tasks = response.json()['data']['items']
        assert all(task['status'] == 'completed' for task in tasks)
        assert sum(task['trace']['model_calls'] for task in tasks) <= 4
        checks.append('durable_index_retrieval_and_rebuild_tasks_complete')

    private = ROOT / ('.local/m2-browser.json' if evidence_name == 'm2-live-index' else '.local/m3-index-browser.json')
    private.write_text(json.dumps({'account': accounts[0], 'doc_id': second['doc_id']}, ensure_ascii=False), encoding='utf-8')
    report = {'recorded_at': datetime.now(timezone.utc).isoformat(), 'environment': 'isolated loopback API/MySQL/Chroma',
              'source': 'synthetic authored teaching material', 'checks': checks, 'passed': len(checks),
              'elapsed_seconds': round(time.perf_counter()-started, 2), 'retrieval_trace': retrieval['trace'],
              'embedding_request_upper_bound': 4, 'chat_requests': 0, 'billed_currency': None,
              'durable_tasks': [{key: task[key] for key in ('kind', 'status', 'trace')} for task in tasks]}
    (ROOT / f'docs/evidence/{evidence_name}.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(report, ensure_ascii=True))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--confirm-four-small-embeddings', action='store_true', required=True)
    parser.add_argument('--evidence-name', choices=['m2-live-index', 'm3-live-index'], default='m2-live-index')
    args = parser.parse_args()
    asyncio.run(main(args.evidence_name))
