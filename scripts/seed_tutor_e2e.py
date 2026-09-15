"""Loopback-only tutor checkpoints, committed before a worker can claim the job."""
import argparse
import asyncio
import hashlib
import json
import uuid

from run_local import configure

configure()

from langchain_core.documents import Document
from app.core.db import close_mysql_pool, connect_mysql
from app.models.evidence import evidence_from_row
from app.models.tutor import TutorTurn
from app.repositories import rag_index_repository as index, job_repository as jobs, tutor_repository
from app.services import tutor_service, vector_store_service as vectors

TEXT = '主动回忆可以暴露遗漏。学习时先用自己的话解释概念，再对照原文检查。合成验收材料，不代表学习效果实验。'


async def main(args):
    await connect_mysql()
    try:
        async with index.transaction() as cur:
            await cur.execute('SELECT username FROM account_credentials WHERE user_id=%s', (args.user_id,))
            row = await cur.fetchone()
            if not row or not row['username'].startswith('e2e_'):
                raise ValueError('Only synthetic e2e accounts are allowed')
        if args.prepare:
            doc_id = 'doc_' + uuid.uuid4().hex
            version = vectors.index_version()
            doc = await index.reserve(doc_id, args.user_id, '辅导恢复验收.md', 'md', len(TEXT.encode()), hashlib.sha256(TEXT.encode()).hexdigest(), version, 10)
            await index.publish(doc_id, args.user_id, 1, version, [Document(page_content=TEXT, metadata={'chunk_id': 'tutor_e2e'})])
            await jobs.cancel(doc['task_id'], args.user_id)
            print(json.dumps({'docId': doc_id}))
            return
        if args.release:
            async with index.transaction() as cur:
                await cur.execute("SELECT * FROM learning_jobs WHERE task_id=%s AND user_id=%s AND kind='tutor' AND status='running' FOR UPDATE", (args.release, args.user_id))
                job = jobs.decode(await cur.fetchone())
                if not job or job['state_json'].get('fixture') != 'e2e-tutor-hold':
                    raise ValueError('Only a synthetic held tutor may be released')
                await cur.execute('UPDATE learning_jobs SET lease_until=UTC_TIMESTAMP()-INTERVAL 1 SECOND WHERE task_id=%s', (args.release,))
            print('synthetic_tutor_released')
            return
        session = await tutor_repository.get(args.session_id, args.user_id)
        rows = await index.scoped_chunks(args.user_id, session['config_json']['doc_ids'], vectors.index_version())
        if len(rows) != 1 or rows[0]['content'] != TEXT:
            raise ValueError('Only the explicit synthetic tutor document may be checkpointed')
        evidence = evidence_from_row(rows[0], 'E1').model_dump()
        reply = {'status': 'hint', 'hint': '先不看笔记，回想刚读过的核心概念。', 'question': '你能用自己的话解释一个概念吗？',
                 'citations': [{'evidence_id': 'E1', 'quote': '主动回忆可以暴露遗漏'}], 'diagnosis': None, 'practice': {'count': 2, 'focus': '主动回忆'}}
        original = jobs.insert
        async def held(cur, user_id, kind, payload, key, status='queued'):
            task = await original(cur, user_id, kind, payload, key, status)
            if kind != 'tutor' or user_id != args.user_id or task['replayed']:
                raise ValueError('Only a new synthetic tutor job may be checkpointed')
            state = {'fixture': 'e2e-tutor-hold', 'checkpoints': {'tutor_evidence': {'status': 'ok', 'evidence': [evidence]},
                     'tutor_coach': {'output': [{'content': json.dumps(reply, ensure_ascii=False), 'finish_reason': 'stop'}]}}}
            await cur.execute("UPDATE learning_jobs SET status='running',stage='tutor_coach',lease_token=%s,lease_until=UTC_TIMESTAMP()+INTERVAL 120 SECOND,claims=1,started_at=UTC_TIMESTAMP(),state_json=%s WHERE task_id=%s",
                              (uuid.uuid4().hex, jobs.encoded(state), task['task_id']))
            return task
        jobs.insert = held
        try:
            task = await tutor_service.turn(args.session_id, args.user_id, TutorTurn(version=args.version, message=args.message), uuid.uuid4().hex)
        finally:
            jobs.insert = original
        print(json.dumps({'taskId': task['task_id'], 'sessionId': args.session_id}))
    finally:
        await close_mysql_pool()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--user-id', type=int, required=True)
    parser.add_argument('--prepare', action='store_true')
    parser.add_argument('--session-id')
    parser.add_argument('--version', type=int, default=0)
    parser.add_argument('--message', default='请从一个小问题开始帮助我理解。')
    parser.add_argument('--release')
    asyncio.run(main(parser.parse_args()))
