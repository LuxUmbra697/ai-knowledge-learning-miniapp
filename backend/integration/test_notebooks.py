"""Real database boundaries for explicit, owner-scoped error notebooks."""
import asyncio

import pytest
from app.services import learning_state_service as learning
from app.services.grading_service import AnswerSubmission, submit_question
from fastapi import HTTPException
from pydantic import ValidationError
from test_learning_state import fixture


@pytest.mark.asyncio
async def test_explicit_membership_is_idempotent_owned_and_does_not_change_learning(users):
    from app.services import notebook_service as books
    quiz = await fixture(users[0])
    await submit_question(quiz, users[0], AnswerSubmission(question_id='q1', selected_answers=['B']))
    card = (await learning.cards(users[0], 'wrong'))[0]
    assert await books.list_notebooks(users[0]) == []
    first, duplicate = await asyncio.gather(*[books.create(users[0], books.NotebookName(name='  线性代数  ')) for _ in range(2)])
    assert first['notebook_id'] == duplicate['notebook_id']
    notebook = first['notebook_id']
    other = await books.create(users[1], books.NotebookName(name='线性代数'))
    assert other['notebook_id'] != notebook
    assert (await books.list_notebooks(users[0]))[0]['question_count'] == 0
    for owner, target in [(users[1], notebook), (users[0], other['notebook_id'])]:
        with pytest.raises(HTTPException) as error:
            await books.add(target, owner, card['card_id'])
        assert error.value.status_code == 404
    await books.add(notebook, users[0], card['card_id'])
    await books.add(notebook, users[0], card['card_id'])
    assert (await books.list_notebooks(users[0]))[0]['question_count'] == 1
    rows = await books.items(notebook, users[0])
    assert len(rows) == 1 and 'answer' not in rows[0]['question']
    assert (await learning.summary(users[0]))['concepts'][0]['attempts'] == 1
    with pytest.raises(HTTPException) as error:
        await books.items(notebook, users[1])
    assert error.value.status_code == 404
    await books.remove(notebook, users[0], card['card_id'])
    await books.remove(notebook, users[0], card['card_id'])
    assert await books.items(notebook, users[0]) == []
    assert len(await learning.cards(users[0], 'wrong')) == 1


@pytest.mark.asyncio
async def test_notebook_rename_conflict_delete_and_correct_question_rejection(users):
    from app.services import notebook_service as books
    quiz = await fixture(users[0])
    await submit_question(quiz, users[0], AnswerSubmission(question_id='q1', selected_answers=['A']))
    card = (await learning.cards(users[0], 'all'))[0]
    book = await books.create(users[0], books.NotebookName(name='暂存'))
    with pytest.raises(HTTPException) as error:
        await books.add(book['notebook_id'], users[0], card['card_id'])
    assert error.value.status_code == 422
    updated = await books.rename(book['notebook_id'], users[0], books.NotebookRename(name='长期复习', version=1))
    assert updated['name'] == '长期复习' and updated['version'] == 2
    with pytest.raises(HTTPException) as error:
        await books.rename(book['notebook_id'], users[0], books.NotebookRename(name='另一设备', version=1))
    assert error.value.status_code == 409
    with pytest.raises(HTTPException) as error:
        await books.delete(book['notebook_id'], users[0], 1)
    assert error.value.status_code == 409
    with pytest.raises(HTTPException) as error:
        await books.delete(book['notebook_id'], users[1], 2)
    assert error.value.status_code == 404
    await books.delete(book['notebook_id'], users[0], 2)
    assert await books.list_notebooks(users[0]) == []
    assert len(await learning.cards(users[0], 'all')) == 1
    for value in ['', '   ', '<script>alert(1)</script>', 'a' * 81, '\x00text']:
        with pytest.raises(ValidationError):
            books.NotebookName(name=value)
