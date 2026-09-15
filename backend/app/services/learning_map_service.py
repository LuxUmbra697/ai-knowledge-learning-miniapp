"""Owner-scoped persisted maps; current source visibility participates in their content hash."""
import json

from fastapi import HTTPException

from app.learning.maps import build_map
from app.repositories.rag_index_repository import transaction
from app.services.history_service import get_quiz_detail


async def get_map(quiz_id, user_id):
    detail = await get_quiz_detail(quiz_id, user_id)
    if detail is None:
        raise HTTPException(404, '练习不存在')
    try:
        data = detail.model_dump()
        graph = build_map(data['title'], data['questions'], data['answer_records'])
    except ValueError as error:
        raise HTTPException(409, '完成全部作答后可查看学习梳理图') from error
    # This is a derived cache, not a learning-state mutation. Revalidate evidence on every read.
    async with transaction() as cur:
        await cur.execute('SELECT quiz_id FROM quiz_sessions WHERE quiz_id=%s AND user_id=%s FOR UPDATE', (quiz_id, user_id))
        if not await cur.fetchone():
            raise HTTPException(404, '练习不存在')
        await cur.execute('INSERT INTO quiz_learning_maps(user_id,quiz_id,source_hash,graph_json,updated_at) '
                          'VALUES(%s,%s,%s,%s,UTC_TIMESTAMP()) ON DUPLICATE KEY UPDATE '
                          'source_hash=VALUES(source_hash),graph_json=VALUES(graph_json),updated_at=VALUES(updated_at)',
                          (user_id, quiz_id, graph['source_hash'], json.dumps(graph, ensure_ascii=False)))
    return graph
