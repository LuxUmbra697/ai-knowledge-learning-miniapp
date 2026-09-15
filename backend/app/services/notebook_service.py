"""Explicit notebook membership; no scoring, scheduling or XP side effects."""
import hashlib
import unicodedata
import uuid

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.repositories.rag_index_repository import transaction
from app.services import learning_state_service as learning


class NotebookName(BaseModel):
    model_config = ConfigDict(extra='forbid')
    name: str = Field(min_length=1, max_length=80)

    @field_validator('name')
    @classmethod
    def clean_name(cls, value):
        if any(unicodedata.category(c).startswith('C') or c in '<>' for c in value):
            raise ValueError('名称不能包含控制字符或 HTML 标记')
        value = ' '.join(unicodedata.normalize('NFKC', value).split())
        if not 1 <= len(value) <= 80:
            raise ValueError('名称需要 1 至 80 个字符')
        return value


class NotebookRename(NotebookName):
    version: int = Field(ge=1, strict=True)


class NotebookQuestion(BaseModel):
    model_config = ConfigDict(extra='forbid')
    quiz_id: str = Field(min_length=1, max_length=64)
    question_id: str = Field(min_length=1, max_length=64)


def name_key(name):
    return hashlib.sha256(name.casefold().encode()).hexdigest()


async def owned(cur, notebook_id, user_id):
    await cur.execute('SELECT notebook_id,name,version FROM learning_notebooks WHERE notebook_id=%s AND user_id=%s FOR UPDATE', (notebook_id, user_id))
    row = await cur.fetchone()
    if not row:
        raise HTTPException(404, '错题本不存在')
    return row


async def owner_lock(cur, user_id):
    await cur.execute('SELECT id FROM users WHERE id=%s FOR UPDATE', (user_id,))
    if not await cur.fetchone():
        raise HTTPException(404, '账号不存在')


async def list_notebooks(user_id):
    async with transaction() as cur:
        await cur.execute('SELECT n.notebook_id,n.name,n.version,COUNT(i.question_id) AS question_count FROM learning_notebooks n '
                          'LEFT JOIN learning_notebook_items i ON n.notebook_id=i.notebook_id AND n.user_id=i.user_id '
                          'WHERE n.user_id=%s GROUP BY n.notebook_id,n.name,n.version ORDER BY n.name,n.notebook_id', (user_id,))
        return list(await cur.fetchall())


async def create(user_id, request):
    async with transaction() as cur:
        await owner_lock(cur, user_id)
        await cur.execute('SELECT notebook_id,name,version FROM learning_notebooks WHERE user_id=%s AND name_key=%s', (user_id, name_key(request.name)))
        existing = await cur.fetchone()
        if existing:
            return existing
        await cur.execute('SELECT COUNT(*) AS n FROM learning_notebooks WHERE user_id=%s', (user_id,))
        if (await cur.fetchone())['n'] >= 30:
            raise HTTPException(409, '最多保留 30 个错题本，请先整理已有错题本')
        book_id, now = 'book_' + uuid.uuid4().hex, learning.sql_time(learning.utcnow())
        await cur.execute('INSERT INTO learning_notebooks(notebook_id,user_id,name,name_key,created_at,updated_at) VALUES(%s,%s,%s,%s,%s,%s)',
                          (book_id, user_id, request.name, name_key(request.name), now, now))
        return {'notebook_id': book_id, 'name': request.name, 'version': 1}


async def rename(notebook_id, user_id, request):
    async with transaction() as cur:
        await owner_lock(cur, user_id)
        book = await owned(cur, notebook_id, user_id)
        if book['version'] != request.version:
            raise HTTPException(409, '错题本已更新，请刷新后重试')
        await cur.execute('SELECT notebook_id FROM learning_notebooks WHERE user_id=%s AND name_key=%s AND notebook_id<>%s',
                          (user_id, name_key(request.name), notebook_id))
        if await cur.fetchone():
            raise HTTPException(409, '已有同名错题本')
        if book['name'] != request.name:
            await cur.execute('UPDATE learning_notebooks SET name=%s,name_key=%s,version=version+1,updated_at=%s WHERE notebook_id=%s AND user_id=%s',
                              (request.name, name_key(request.name), learning.sql_time(learning.utcnow()), notebook_id, user_id))
            book.update(name=request.name, version=book['version'] + 1)
        return book


async def add(notebook_id, user_id, card_id):
    async with transaction() as cur:
        await owned(cur, notebook_id, user_id)
        await cur.execute('SELECT quiz_id,question_id,wrong_count FROM learning_cards WHERE card_id=%s AND user_id=%s', (card_id, user_id))
        card = await cur.fetchone()
        if not card:
            raise HTTPException(404, '错题记录不存在')
        if card['wrong_count'] < 1:
            raise HTTPException(422, '只能将已有答错记录的题目加入错题本')
        scope = (notebook_id, user_id, card['quiz_id'], card['question_id'])
        await cur.execute('SELECT question_id FROM learning_notebook_items WHERE notebook_id=%s AND user_id=%s AND quiz_id=%s AND question_id=%s', scope)
        if await cur.fetchone():
            return {'added': False}
        now = learning.sql_time(learning.utcnow())
        await cur.execute('INSERT INTO learning_notebook_items(notebook_id,user_id,quiz_id,question_id,created_at) VALUES(%s,%s,%s,%s,%s)', (*scope, now))
        await cur.execute('UPDATE learning_notebooks SET version=version+1,updated_at=%s WHERE notebook_id=%s AND user_id=%s', (now, notebook_id, user_id))
        return {'added': True}


async def add_question(notebook_id, user_id, request):
    async with transaction() as cur:
        await cur.execute('SELECT card_id FROM learning_cards WHERE user_id=%s AND quiz_id=%s AND question_id=%s', (user_id, request.quiz_id, request.question_id))
        card = await cur.fetchone()
    if not card:
        raise HTTPException(404, '没有可归档的错题记录')
    return await add(notebook_id, user_id, card['card_id'])


async def items(notebook_id, user_id):
    return await learning.cards(user_id, 'wrong', notebook_id=notebook_id)


async def remove(notebook_id, user_id, card_id):
    async with transaction() as cur:
        await owned(cur, notebook_id, user_id)
        await cur.execute('SELECT quiz_id,question_id FROM learning_cards WHERE user_id=%s AND card_id=%s', (user_id, card_id))
        card = await cur.fetchone()
        if not card:
            raise HTTPException(404, '错题记录不存在')
        await cur.execute('DELETE FROM learning_notebook_items WHERE notebook_id=%s AND user_id=%s AND quiz_id=%s AND question_id=%s',
                          (notebook_id, user_id, card['quiz_id'], card['question_id']))
        if cur.rowcount:
            await cur.execute('UPDATE learning_notebooks SET version=version+1,updated_at=%s WHERE notebook_id=%s AND user_id=%s',
                              (learning.sql_time(learning.utcnow()), notebook_id, user_id))


async def delete(notebook_id, user_id, version):
    async with transaction() as cur:
        book = await owned(cur, notebook_id, user_id)
        if book['version'] != version:
            raise HTTPException(409, '错题本已更新，请刷新后再确认删除')
        await cur.execute('DELETE FROM learning_notebooks WHERE notebook_id=%s AND user_id=%s', (notebook_id, user_id))
