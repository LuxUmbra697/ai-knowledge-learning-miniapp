"""Revalidate disclosed quiz quotations against current, owner-scoped source records."""
from fastapi import HTTPException
import structlog

from app.repositories.rag_index_repository import get_chunk

logger = structlog.get_logger()


async def visible_question(question, user_id):
    citations = []
    for citation in question.get('citations', []):
        try:
            row = await get_chunk(user_id, citation['doc_id'], citation['chunk_id'], citation['revision'])
            if row['index_version'] != citation['index_version'] or citation['quote'] not in row['content']:
                raise HTTPException(404, 'Stale evidence')
            citations.append({**citation, 'status': 'verified'})
        except Exception as error:
            # Submission already committed; an evidence outage must not invite a second answer.
            if not isinstance(error, HTTPException):
                logger.warning('quiz_evidence_unavailable', error_type=type(error).__name__)
            citations.append({'evidence_id': citation.get('evidence_id', ''), 'status': 'unavailable'})
    return {**question, 'citations': citations} if 'citations' in question else dict(question)
