"""Revalidate a real model's saved local practice without calling any provider."""
import asyncio
import json

from run_local import ROOT, configure


async def main():
    configure(False)
    from app.core.db import connect_mysql, close_mysql_pool
    from app.llm.quiz_chain import validate_quiz
    from app.repositories.quiz_repository import get_quiz_detail
    from app.services.grading_service import grade_answer

    identity = json.loads((ROOT / '.local/m2-browser.json').read_text(encoding='utf8'))['account']
    quiz_id = json.loads((ROOT / '.local/practice-browser.json').read_text(encoding='utf8'))['quizId']
    await connect_mysql()
    try:
        detail = await get_quiz_detail(quiz_id, identity['user']['id'])
        if not detail:
            raise RuntimeError('Owned local practice fixture is missing')
        quiz = validate_quiz(detail, 5, 'mixed')
        questions = {question.id: question.model_dump() for question in quiz.questions}
        for record in detail['answer_records']:
            assert grade_answer(questions[record['question_id']], record['selected_answers'], record['duration_ms']) == record
        assert len(detail['answer_records']) == len(questions)
        print(json.dumps({'saved_real_output_validated': True, 'questions': len(questions), 'provider_calls': 0}))
    finally:
        await close_mysql_pool()


if __name__ == '__main__':
    asyncio.run(main())
