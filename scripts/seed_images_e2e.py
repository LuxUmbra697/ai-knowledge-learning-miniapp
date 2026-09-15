"""Synthetic image state fixtures, atomically checkpointed to prevent any provider calls."""
import argparse
import asyncio
import json
import uuid
from types import SimpleNamespace

from run_local import configure

configure()

from app.core.db import close_mysql_pool, connect_mysql
from app.models.quiz import Question
from app.repositories import job_repository as jobs, quiz_image_repository as assets
from app.repositories.rag_index_repository import transaction


async def main(user_id, release):
    await connect_mysql()
    try:
        async with transaction() as cur:
            await cur.execute('SELECT username FROM account_credentials WHERE user_id=%s', (user_id,))
            row = await cur.fetchone()
            if not row or not row['username'].startswith('e2e_'):
                raise ValueError('Only synthetic e2e accounts are allowed')
            if release:
                await cur.execute("SELECT * FROM learning_jobs WHERE task_id=%s AND user_id=%s AND kind='image' AND status='running' FOR UPDATE", (release, user_id))
                job = jobs.decode(await cur.fetchone())
                if not job or job['state_json'].get('fixture') != 'e2e-image-hold':
                    raise ValueError('Only a synthetic held image may be released')
                await cur.execute('UPDATE learning_jobs SET lease_until=UTC_TIMESTAMP()-INTERVAL 1 SECOND WHERE task_id=%s', (release,))
                print('synthetic_image_released')
                return
            quiz_id = 'quiz_e2e_' + uuid.uuid4().hex
            question = Question(id='q1', type='single', stem='合成验收：配图失败时，已经生成的文字练习是否应当保留？',
                                options=[{'key': 'A', 'text': '应当保留，可以继续作答'}, {'key': 'B', 'text': '删除文字题库'}],
                                answer=['A'], explanation='配图任务独立于已保存的文字题库。', knowledge_point='任务边界', difficulty='easy')
            await cur.execute('INSERT INTO quiz_sessions(quiz_id,user_id,title,summary,user_input,questions_json) VALUES(%s,%s,%s,%s,%s,%s)',
                              (quiz_id, user_id, '配图取消与失败验收', '合成测试题，未调用模型', 'synthetic', jobs.encoded([question.model_dump()])))
            context = SimpleNamespace(user_id=user_id, task_id='seed_' + uuid.uuid4().hex, payload={'doc_ids': [], 'scope': []})
            task_id = await assets.attach(cur, context, quiz_id, [question])
            await cur.execute('UPDATE quiz_sessions SET questions_json=%s WHERE quiz_id=%s', (jobs.encoded([question.model_dump()]), quiz_id))
            state = {'fixture': 'e2e-image-hold', 'checkpoints': {'image_saved_1': {'asset_id': question.image_asset_id, 'state': 'failed', 'error_code': 'SyntheticFixture'}}}
            await cur.execute("UPDATE learning_jobs SET status='running',stage='image_1',lease_token=%s,lease_until=UTC_TIMESTAMP()+INTERVAL 120 SECOND,claims=1,started_at=UTC_TIMESTAMP(),state_json=%s WHERE task_id=%s",
                              (uuid.uuid4().hex, jobs.encoded(state), task_id))
            print(json.dumps({'quizId': quiz_id, 'taskId': task_id, 'assetId': question.image_asset_id}))
    finally:
        await close_mysql_pool()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--user-id', type=int, required=True)
    parser.add_argument('--release')
    args = parser.parse_args()
    asyncio.run(main(args.user_id, args.release))
