"""Seed only the isolated loopback database for browser contract verification."""
import argparse
import asyncio
import uuid

from run_local import configure

configure()

from app.core.db import connect_mysql, close_mysql_pool, get_mysql_pool
from app.repositories.quiz_repository import save_quiz_session


async def main(user_id: int, staged_upload=False):
    await connect_mysql()
    try:
        async with get_mysql_pool().acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute("SELECT username FROM account_credentials WHERE user_id=%s", (user_id,))
                row = await cur.fetchone()
                if not row or not row[0].startswith("e2e_"):
                    raise ValueError("Only synthetic e2e accounts may receive fixtures")
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
        await save_quiz_session(quiz_id, user_id, "学习方法与证据意识", "合成验收题库，验证作答流程", "确定性浏览器验收", questions)
        print(quiz_id)
    finally:
        await close_mysql_pool()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--user-id", required=True, type=int)
    parser.add_argument('--staged-upload', action='store_true')
    args = parser.parse_args()
    asyncio.run(main(args.user_id, args.staged_upload))
