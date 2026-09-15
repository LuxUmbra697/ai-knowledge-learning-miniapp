"""Character canon, memory provenance and structured dialogue boundaries."""
import pytest
from typing import get_args
from pydantic import ValidationError

from app.companions.catalog import character, story, CATALOG
from app.models.companion import MemoryItem, CompanionTurn, CharacterId, ResetConversation
from app.llm.companion_chain import validate_reply


def test_character_canon_and_progression_are_distinct_and_stable():
    assert set(get_args(CharacterId)) == set(CATALOG)
    assert character('pink')['primary'] != character('orange')['primary']
    assert character('pink')['age'] >= 18 and character('orange')['age'] >= 18
    for identity in ('pink', 'orange'):
        first = story(identity, 0)
        complete = story(identity, 12)
        assert len(first) == 1 and len(complete) == 4
        assert first[0] == complete[0]
        assert len({part['id'] for part in complete}) == 4
    with pytest.raises(ValueError):
        character('../other-user')


def test_companion_commands_cannot_choose_identity_or_store_credentials():
    with pytest.raises(ValidationError):
        CompanionTurn(version=0, message='hello', user_id=2)
    with pytest.raises(ValidationError):
        ResetConversation(version=0, mode='all', confirmed=False)
    with pytest.raises(ValidationError):
        MemoryItem(id='name', kind='name', text='sk-secret12345678901234567890123456')
    with pytest.raises(ValidationError):
        MemoryItem(id='name', kind='name', text='我的密码是1234567890')


def test_reply_memory_references_and_suggestions_must_have_actual_support():
    material = {'message': '我喜欢用番茄钟学习', 'memories': [{'id': 'style', 'text': '喜欢清晰步骤'}]}
    valid = {'dialogue': '那就给这段学习留一个小小的刻度吧。', 'emotion': 'warm', 'action': 'nod',
             'used_memory_ids': ['style'], 'memory_suggestion': {'kind': 'study', 'text': '我喜欢用番茄钟学习'}}
    assert validate_reply(valid, material)['emotion'] == 'warm'
    for change in ({'used_memory_ids': ['other-user-memory']},
                   {'memory_suggestion': {'kind': 'study', 'text': '未说过的偏好'}},
                   {'emotion': 'arbitrary-script'}, {'dialogue': '<script>bad()</script>'}):
        with pytest.raises(ValueError):
            validate_reply({**valid, **change}, material)
