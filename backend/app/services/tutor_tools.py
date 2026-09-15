"""Read-only, schema-checked capabilities bound to the authenticated session."""
from dataclasses import dataclass, field

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field

from app.repositories.rag_index_repository import transaction
from app.services import retrieval_service


class EmptyArguments(BaseModel):
    model_config = ConfigDict(extra='forbid')


class RetrieveArguments(EmptyArguments):
    query: str = Field(min_length=1, max_length=1000)


class PracticeArguments(EmptyArguments):
    count: int = Field(ge=1, le=5, strict=True)
    focus: str = Field(min_length=1, max_length=120)


TOOL_SCHEMAS = {'retrieve_notes': RetrieveArguments, 'read_learning_state': EmptyArguments,
                'review_queue': EmptyArguments, 'propose_practice': PracticeArguments}


@dataclass(frozen=True)
class TutorTools:
    user_id: int
    doc_ids: tuple[str, ...]
    context: object
    calls: list[str] = field(default_factory=list, init=False, repr=False)

    async def call(self, name, arguments):
        if name not in TOOL_SCHEMAS:
            raise HTTPException(422, '辅导工具不在允许列表内')
        args = TOOL_SCHEMAS[name].model_validate(arguments)
        if len(self.calls) >= 4:
            raise HTTPException(429, '本轮辅导已达到工具次数上限')
        self.calls.append(name)
        if name == 'retrieve_notes':
            if not self.doc_ids:
                return {'status': 'empty', 'evidence': []}
            result = await retrieval_service.retrieve(self.user_id, list(self.doc_ids), args.query, mode='rerank', context=self.context)
            return {'status': result.status, 'evidence': [item.model_dump() for item in result.evidence], 'trace': result.trace}
        if name == 'propose_practice':
            return {'count': args.count, 'focus': args.focus, 'doc_id': self.doc_ids[0] if self.doc_ids else None,
                    'requires_confirmation': True, 'created': False}
        async with transaction() as cur:
            if name == 'read_learning_state':
                await cur.execute('SELECT label,mastery,attempts,mapping_confidence FROM learning_concepts WHERE user_id=%s ORDER BY mastery,concept_id LIMIT 5', (self.user_id,))
                return {'concepts': list(await cur.fetchall()), 'basis': 'Default BKT estimates, not a measured knowledge test'}
            await cur.execute('SELECT card_id,due_at FROM learning_cards WHERE user_id=%s AND due_at<=UTC_TIMESTAMP() ORDER BY due_at,card_id LIMIT 5', (self.user_id,))
            return {'items': [{'card_id': row['card_id'], 'due_at': row['due_at'].isoformat() + 'Z'} for row in await cur.fetchall()], 'limit': 5}
