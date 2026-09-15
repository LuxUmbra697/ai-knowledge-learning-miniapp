"""Synthetic five-type UI fixtures; restricted to local e2e accounts, never real providers."""
import argparse
import asyncio
import json
import uuid

from run_local import configure

configure(False)

from app.core.db import close_mysql_pool, connect_mysql
from app.repositories import job_repository as jobs, quiz_repository as quizzes
from app.repositories.rag_index_repository import transaction
from app.services.grading_service import validate_selection

ANSWER = '主动提取记忆，检验理解。'
QUESTIONS = [
    dict(id='q1', type='single', stem='哪种做法是主动回忆？', options=[dict(key='A', text='不看笔记解释知识'), dict(key='B', text='只数页数')], answer=['A'], explanation='主动提取已有知识。', knowledge_point='主动回忆', difficulty='easy'),
    dict(id='q2', type='multiple', stem='复盘需要哪些记录？', options=[dict(key='A', text='自己的回答'), dict(key='B', text='原文证据'), dict(key='C', text='页面颜色')], answer=['A', 'B'], explanation='回答与证据形成对照。', knowledge_point='复盘', difficulty='easy'),
    dict(id='q3', type='judge', stem='没有学习记录，也能宣称完成个人参数训练。', options=[dict(key='A', text='正确'), dict(key='B', text='错误')], answer=['B'], explanation='冷启动使用默认参数。', knowledge_point='冷启动', difficulty='easy'),
    dict(id='q4', type='fill', stem='主动回忆需要主动 ___ 记忆，用于检验 ___。', options=[], answer=['提取', '理解'], accepted_answers=[['提取', '回忆'], ['理解', '掌握情况']], explanation='这是用于验证顺序判分的合成题目。', knowledge_point='主动回忆', difficulty='easy'),
    dict(id='q5', type='written', stem='说明主动回忆的机制和用途。', options=[], answer=['主动提取记忆以检验理解。'], rubric=['解释主动提取机制', '说明检验理解的用途'], explanation='主动回忆通过提取检验理解。', knowledge_point='主动回忆', difficulty='easy'),
]
VERDICT = dict(criteria=[dict(index=0, met=True, quote='主动提取记忆', feedback='覆盖提取机制'), dict(index=1, met=True, quote='检验理解', feedback='覆盖检验用途')], contradiction=False, uncertain=False, feedback='两个评分要点均已覆盖。这是恢复流程的确定性测试结果。')


async def main(args):
    await connect_mysql()
    try:
        async with transaction() as cur:
            await cur.execute('SELECT username FROM account_credentials WHERE user_id=%s', (args.user_id,))
            account = await cur.fetchone()
            if not account or not account['username'].startswith('e2e_'):
                raise ValueError('Only isolated synthetic accounts are permitted')
            if args.release:
                await cur.execute("SELECT state_json FROM learning_jobs WHERE task_id=%s AND user_id=%s AND kind='grade' AND status='running' FOR UPDATE", (args.release, args.user_id))
                row = await cur.fetchone()
                if not row or json.loads(row['state_json']).get('fixture') != 'e2e-written-hold':
                    raise ValueError('Not a held synthetic grading task')
                await cur.execute('UPDATE learning_jobs SET lease_until=UTC_TIMESTAMP()-INTERVAL 1 SECOND WHERE task_id=%s', (args.release,))
                print('synthetic_grade_released')
                return
        quiz_id = 'quiz_e2e_' + uuid.uuid4().hex[:12]
        await quizzes.save_quiz_session(quiz_id, args.user_id, '五种题型 · 学习方法练习', '确定性功能验收，不是效果实验', 'Synthetic UI fixture', QUESTIONS)
        payload = dict(quiz_id=quiz_id, question_id='q5', card_id=None, version=None, selected_answers=validate_selection(QUESTIONS[-1], [ANSWER]), duration_ms=0, title=QUESTIONS[-1]['stem'])
        async with transaction() as cur:
            task = await jobs.insert(cur, args.user_id, 'grade', payload, uuid.uuid4().hex)
            state = dict(fixture='e2e-written-hold', checkpoints={'written_grade': {'output': [{'content': json.dumps(VERDICT, ensure_ascii=False), 'finish_reason': 'stop'}]}})
            await cur.execute("UPDATE learning_jobs SET status='running',stage='written_grade',lease_token=%s,lease_until=UTC_TIMESTAMP()+INTERVAL 120 SECOND,claims=1,started_at=UTC_TIMESTAMP(),state_json=%s WHERE task_id=%s",
                              (uuid.uuid4().hex, jobs.encoded(state), task['task_id']))
        print(json.dumps(dict(quizId=quiz_id, taskId=task['task_id'])))
    finally:
        await close_mysql_pool()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--user-id', type=int, required=True)
    parser.add_argument('--release')
    asyncio.run(main(parser.parse_args()))
