"""Private practice must carry exact, owned evidence without disclosing it before an answer."""
import copy
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from app.llm.quiz_chain import validate_quiz
from app.services.grading_service import public_quiz


def source(label='E1'):
    return dict(id=label, doc_id='doc_owned', chunk_id=label, revision=2, index_version='v1',
                file_name='Synthetic notes.md', page=3, section='Recovery', content_hash='a' * 64,
                content='A saved checkpoint enables task recovery.', source_type='private_document')


def cited_output(sample):
    data = copy.deepcopy({key: sample[key] for key in ('title', 'summary', 'questions')})
    for i, question in enumerate(data['questions']):
        question['citations'] = [{'evidence_id': f'E{1 + i % 2}', 'quote': 'saved checkpoint'}]
    return data


@pytest.mark.parametrize('corruption', ['missing', 'unknown', 'paraphrase', 'duplicate', 'forged_location', 'coverage', 'blank'])
def test_rejects_unsupported_or_uncovered_private_questions(sample_quiz_response_data, corruption):
    data = cited_output(sample_quiz_response_data)
    cited = data['questions'][0]['citations'][0]
    if corruption == 'missing': data['questions'][0]['citations'] = []
    elif corruption == 'unknown': cited['evidence_id'] = 'other-user'
    elif corruption == 'paraphrase': cited['quote'] = 'A checkpoint makes recovery perfect.'
    elif corruption == 'duplicate': data['questions'][0]['citations'] *= 2
    elif corruption == 'forged_location': cited['doc_id'] = 'doc_someone_else'
    elif corruption == 'coverage':
        for question in data['questions']: question['citations'][0]['evidence_id'] = 'E1'
    elif corruption == 'blank': cited['quote'] = '  '
    with pytest.raises(ValueError):
        validate_quiz(data, 5, 'mixed', evidence=[source(), source('E2')])


def test_valid_quotes_receive_only_server_locations_and_remain_hidden(sample_quiz_response_data):
    result = validate_quiz(cited_output(sample_quiz_response_data), 5, 'mixed', evidence=[source(), source('E2')])
    citation = result.questions[0].citations[0]
    assert citation.doc_id == 'doc_owned' and citation.page == 3 and citation.revision == 2
    hidden = public_quiz(result.model_dump())
    assert all('citations' not in q for q in hidden['questions'])
    revealed = public_quiz(result.model_dump(), {result.questions[0].id})
    assert revealed['questions'][0]['citations'][0]['quote'] == 'saved checkpoint'


def test_unscoped_generation_cannot_forge_private_citations(sample_quiz_response_data):
    with pytest.raises(ValueError):
        validate_quiz(cited_output(sample_quiz_response_data), 5, 'mixed')


@pytest.mark.asyncio
@pytest.mark.parametrize('state', ['valid', 'deleted', 'reindexed', 'changed_quote'])
async def test_revealed_citations_are_revalidated_in_the_request_owner_scope(monkeypatch, state):
    from app.services import quiz_evidence_service as service
    chunk = dict(index_version='v1', content=source()['content'])
    if state == 'reindexed': chunk['index_version'] = 'v2'
    if state == 'changed_quote': chunk['content'] = 'Other material'
    lookup = AsyncMock(return_value=chunk, side_effect=HTTPException(404, 'Removed') if state == 'deleted' else None)
    monkeypatch.setattr(service, 'get_chunk', lookup)
    question = {'id': 'q1', 'citations': [{**source(), 'evidence_id': 'E1', 'quote': 'saved checkpoint'}]}
    visible = await service.visible_question(question, 17)
    lookup.assert_awaited_once_with(17, 'doc_owned', 'E1', 2)
    if state == 'valid': assert visible['citations'][0]['quote'] == 'saved checkpoint'
    else: assert visible['citations'] == [{'evidence_id': 'E1', 'status': 'unavailable'}]
    assert question['citations'][0]['quote'] == 'saved checkpoint'
