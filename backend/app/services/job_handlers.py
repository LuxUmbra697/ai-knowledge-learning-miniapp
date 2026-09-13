"""Task handlers use authenticated row ownership; payloads never select arbitrary paths or SQL."""
import asyncio
import hashlib
import structlog
from fastapi import HTTPException

from app.services import knowledge_service, vector_store_service
from app.repositories import rag_index_repository, job_repository
from app.services import grounded_answer_service, retrieval_service

logger = structlog.get_logger()


async def index_document(context):
    payload = context.payload
    if payload['index_version'] != vector_store_service.index_version():
        raise ValueError('索引配置已变化，请重新建立索引')
    path = knowledge_service._stored_path(payload['storage_key'])
    await knowledge_service._process_document(payload['doc_id'], context.user_id, str(path), payload['file_type'],
                                              payload['revision'], payload['index_version'], payload.get('previous'), context)
    return {'doc_id': payload['doc_id'], 'revision': payload['revision']}


def handlers():
    return {'index': index_document, 'answer': answer_question, 'retrieve': retrieve_evidence}


async def validate_scope(context):
    payload = context.payload
    rows = await rag_index_repository.scoped_chunks(context.user_id, payload['doc_ids'], vector_store_service.index_version())
    scope = sorted({(row['doc_id'], row['revision'], row['index_version']) for row in rows})
    if [list(item) for item in scope] != payload['scope']:
        raise HTTPException(409, '材料版本已变化，请重新提交问题')


async def retrieve_evidence(context):
    await validate_scope(context)
    payload = context.payload
    result = await retrieval_service.retrieve(context.user_id, payload['doc_ids'], payload['query'],
                                               mode=payload['mode'], context=context)
    return result.model_dump()


async def answer_question(context):
    await validate_scope(context)
    payload = context.payload
    result = await grounded_answer_service.answer(context.user_id, payload['doc_ids'], payload['query'],
                                                 context=context, mode=payload['mode'])
    failures = {'provider_failed': '回答服务暂不可用，请稍后重试', 'validation_failed': '回答未通过引用校验，请调整问题后重试',
                'retrieval_failed': '暂时无法检索材料，请稍后重试', 'stale_evidence': '材料已变更，请重新提交问题'}
    if result['status'] in failures:
        raise HTTPException(409, failures[result['status']])
    return result


async def maintenance():
    for row in await rag_index_repository.maintenance_rows():
        try:
            path = knowledge_service._stored_path(row['storage_key'])
            if not row['active']:
                await asyncio.to_thread(vector_store_service.delete_document_vectors, row['user_id'], row['doc_id'])
                await asyncio.to_thread(path.unlink, missing_ok=True)
                await rag_index_repository.cleanup_done(row['doc_id'], row['user_id'])
            elif row['job_status'] == 'staging':
                max_bytes = knowledge_service.get_settings().kb_max_file_size_mb * 1024 * 1024
                valid = path.is_file() and path.stat().st_size <= max_bytes and hashlib.sha256(await asyncio.to_thread(path.read_bytes)).hexdigest() == row['file_hash']
                if valid:
                    await job_repository.activate(row['job_id'], row['user_id'])
                else:
                    await job_repository.cancel(row['job_id'], row['user_id'])
                    await rag_index_repository.fail(row['doc_id'], row['user_id'], row['revision'], row['index_version'], '上传中断，请删除此条记录后重新上传')
        except Exception as error:
            logger.warning('index_maintenance_pending', doc_id=row['doc_id'], error_type=type(error).__name__)
