"""Seed only the isolated loopback database for browser contract verification."""
import argparse
import asyncio
import uuid
import json

from run_local import configure

configure()

from app.core.db import connect_mysql, close_mysql_pool, get_mysql_pool
from app.repositories.quiz_repository import save_quiz_session


async def main(user_id: int, staged_upload=False, report_checkpoint=False, release_report=None, quiz_checkpoint=False, release_quiz=None):
    await connect_mysql()
    try:
        async with get_mysql_pool().acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute("SELECT username FROM account_credentials WHERE user_id=%s", (user_id,))
                row = await cur.fetchone()
                if not row or not row[0].startswith("e2e_"):
                    raise ValueError("Only synthetic e2e accounts may receive fixtures")
        if release_report or release_quiz:
            from app.repositories.rag_index_repository import transaction
            from app.repositories import job_repository as jobs
            async with transaction() as cur:
                kind = 'report' if release_report else 'quiz'
                release_id = release_report or release_quiz
                await cur.execute("SELECT * FROM learning_jobs WHERE task_id=%s AND user_id=%s AND kind=%s AND status='running' FOR UPDATE", (release_id, user_id, kind))
                row = jobs.decode(await cur.fetchone())
                if not row or row['state_json'].get('fixture') != f'e2e-{kind}-hold':
                    raise ValueError('Only a held synthetic checkpoint may be released')
                await cur.execute('UPDATE learning_jobs SET lease_until=UTC_TIMESTAMP()-INTERVAL 1 SECOND WHERE task_id=%s', (release_id,))
            print('synthetic_checkpoint_released')
            return
        if staged_upload:
            from app.repositories.rag_index_repository import reserve
            from app.services.vector_store_service import index_version
            import hashlib
            doc_id = 'doc_' + uuid.uuid4().hex
            content = b'Synthetic interrupted-upload fixture; no external calls.'
            task = await reserve(doc_id, user_id, '学习任务恢复与取消验收资料.md', 'md', len(content),
                                 hashlib.sha256(content).hexdigest(), index_version(), 10)
            print(task['task_id'])
            return
        quiz_id = "quiz_e2e_" + uuid.uuid4().hex[:12]
        questions = [
            {"id": "q1", "type": "single", "stem": "阅读笔记后，哪一种做法更有助于检查自己是否真正理解了知识？",
             "options": [{"key": "A", "text": "不看笔记，用自己的话解释核心概念，并检查遗漏。"}, {"key": "B", "text": "只统计阅读过多少页。"}],
             "answer": ["A"], "explanation": "主动回忆能够暴露遗漏；页数本身不证明理解。这是确定性测试题，不是效果实验。",
             "knowledge_point": "主动回忆", "difficulty": "easy"},
            {"id": "q2", "type": "multiple", "stem": "哪些记录可以帮助回顾一次练习？（多选）",
             "options": [{"key": "A", "text": "自己的选择"}, {"key": "B", "text": "对应的知识点与原文证据"}, {"key": "C", "text": "与题目无关的页面装饰"}],
             "answer": ["A", "B"], "explanation": "自己的选择和知识点证据共同帮助定位理解差异。",
             "knowledge_point": "练习复盘", "difficulty": "medium"},
            {"id": "q3", "type": "judge", "stem": "没有作答记录时，系统可以宣称已经为我训练好了个性化学习模型。",
             "options": [{"key": "A", "text": "正确"}, {"key": "B", "text": "错误"}],
             "answer": ["B"], "explanation": "没有足够记录时应使用明确的冷启动策略，不能宣称完成了个性化训练。",
             "knowledge_point": "冷启动", "difficulty": "easy"},
        ]
        if quiz_checkpoint:
            import hashlib
            from langchain_core.documents import Document
            from app.repositories import rag_index_repository as index, job_repository as jobs
            from app.services.vector_store_service import index_version
            doc_id = 'doc_' + uuid.uuid4().hex
            text = '\n'.join(q['explanation'] for q in questions)
            version = index_version()
            doc = await index.reserve(doc_id, user_id, '合成练习恢复验收.md', 'md', len(text.encode()), hashlib.sha256(text.encode()).hexdigest(), version, 10)
            doc_id = doc['doc_id']
            await index.publish(doc_id, user_id, 1, version, [Document(page_content=text, metadata={'chunk_id': 'e2e_chunk'})])
            await jobs.cancel(doc['task_id'], user_id)
            query = '确定性浏览器练习恢复验收'
            payload = dict(query=query, question_count=3, difficulty='mixed', doc_ids=[doc_id], scope=[[doc_id, 1, version]], mode='rerank')
            from app.models.evidence import evidence_from_row
            evidence = evidence_from_row((await index.scoped_chunks(user_id, [doc_id], version))[0], 'E1').model_dump()
            for question in questions:
                question['citations'] = [{'evidence_id': 'E1', 'quote': question['explanation']}]
            source = json.dumps({'source_type': 'private_document', 'evidence': [evidence]}, ensure_ascii=False)
            output = dict(title='学习方法与证据意识', summary='合成验收题库，验证任务恢复与作答流程', questions=questions)
            async with index.transaction() as cur:
                task = await jobs.insert(cur, user_id, 'quiz', payload, uuid.uuid4().hex)
                state = {'fixture': 'e2e-quiz-hold', 'checkpoints': {'quiz_sources': source,
                         'quiz': {'output': [{'content': json.dumps(output, ensure_ascii=False), 'finish_reason': 'stop'}]}}}
                await cur.execute("UPDATE learning_jobs SET status='running',stage='quiz',lease_token=%s,lease_until=UTC_TIMESTAMP()+INTERVAL 120 SECOND,claims=1,started_at=UTC_TIMESTAMP(),state_json=%s WHERE task_id=%s",
                                  (uuid.uuid4().hex, jobs.encoded(state), task['task_id']))
            print(json.dumps({'quizId': 'quiz_' + task['task_id'][4:], 'taskId': task['task_id'], 'docId': doc_id, 'query': query}))
            return
        await save_quiz_session(quiz_id, user_id, "学习方法与证据意识", "合成验收题库，验证作答流程", "确定性浏览器验收", questions)
        if report_checkpoint:
            from app.services.grading_service import submit_question, AnswerSubmission
            from app.repositories import job_repository as jobs
            from app.repositories.rag_index_repository import transaction
            for question in questions:
                await submit_question(quiz_id, user_id, AnswerSubmission(question_id=question['id'], selected_answers=question['answer']))
            report = dict(accuracy=100, mastered_points=[q['knowledge_point'] for q in questions], weak_points=[],
                          three_line_summary=['这是一份合成验收报告。', '三道题均按服务端保存的答案完成。', '恢复过程不调用模型，也不代表真实学习效果。'],
                          advice=['回到原文复习本次知识点。'], share_quote='记录每一步学习。')
            async with transaction() as cur:
                task = await jobs.insert(cur, user_id, 'report', {'quiz_id': quiz_id, 'title': '学习方法与证据意识'}, uuid.uuid4().hex)
                state = {'fixture': 'e2e-report-hold', 'checkpoints': {'report': {'output': [{'content': json.dumps(report, ensure_ascii=False), 'finish_reason': 'stop'}]}}}
                await cur.execute("UPDATE learning_jobs SET status='running',stage='report',lease_token=%s,lease_until=UTC_TIMESTAMP()+INTERVAL 120 SECOND,claims=1,started_at=UTC_TIMESTAMP(),state_json=%s WHERE task_id=%s",
                                  (uuid.uuid4().hex, jobs.encoded(state), task['task_id']))
            print(json.dumps({'quizId': quiz_id, 'taskId': task['task_id']}))
            return
        print(quiz_id)
    finally:
        await close_mysql_pool()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--user-id", required=True, type=int)
    parser.add_argument('--staged-upload', action='store_true')
    parser.add_argument('--report-checkpoint', action='store_true')
    parser.add_argument('--release-report')
    parser.add_argument('--quiz-checkpoint', action='store_true')
    parser.add_argument('--release-quiz')
    args = parser.parse_args()
    asyncio.run(main(args.user_id, args.staged_upload, args.report_checkpoint, args.release_report, args.quiz_checkpoint, args.release_quiz))
