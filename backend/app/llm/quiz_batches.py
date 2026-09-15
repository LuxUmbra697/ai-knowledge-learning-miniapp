"""Resumable bounded generation using the existing shared structured-stage protocol."""
from app.learning.quiz_blueprint import BATCH_SIZE, batches, default_counts
from app.llm.quiz_chain import generate_quiz
from app.llm.structured_stage import StructuredGenerationError


async def generate_quiz_set(user_input, question_count=5, difficulty='mixed', search_context='',
                            context=None, private_source=False, question_counts=None):
    if question_count <= BATCH_SIZE:
        return await generate_quiz(user_input, question_count, difficulty, search_context,
                                   context, private_source, question_counts)
    output = None
    for number, quota in enumerate(batches(question_counts or default_counts(question_count)), 1):
        prior = '\n'.join(q.stem[:180] for q in output.questions) if output else ''
        query = user_input + ('\n此前批次已有题干，请勿重复：\n' + prior if prior else '')
        batch = await generate_quiz(query, sum(quota.values()), difficulty, search_context,
                                   context, private_source, quota, stage=f'quiz_batch_{number}')
        for index, question in enumerate(batch.questions, 1):
            question.id = f'b{number}_q{index}'
        if output is None:
            output = batch
        else:
            output.questions.extend(batch.questions)
    if output is None or len(output.questions) != question_count:
        raise StructuredGenerationError('batch_count_mismatch')
    if len({''.join(q.stem.split()) for q in output.questions}) != question_count:
        raise StructuredGenerationError('duplicate_questions_across_batches')
    return output
