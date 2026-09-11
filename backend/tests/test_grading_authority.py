import pytest
from fastapi import HTTPException

from app.services.grading_service import grade_answer


@pytest.mark.parametrize("kind,answer,selection,correct", [
    ("single", ["A"], ["B"], False),
    ("single", ["A"], ["A"], True),
    ("multiple", ["A", "C"], ["C", "A"], True),
    ("multiple", ["A", "C"], ["A"], False),
    ("judge", ["B"], ["A"], False),
])
def test_server_grades_all_question_types(kind, answer, selection, correct):
    question = {"id": "q1", "type": kind, "options": [{"key": k} for k in "ABC"], "answer": answer}
    result = grade_answer(question, selection, 100)
    assert result["is_correct"] is correct
    assert result["selected_answers"] == sorted(selection)


@pytest.mark.parametrize("selection", [[], ["D"], ["A", "A"], ["A", "B"]])
def test_rejects_forged_options_and_cardinality(selection):
    question = {"id": "q1", "type": "single", "options": [{"key": "A"}, {"key": "B"}], "answer": ["A"]}
    with pytest.raises(HTTPException) as error:
        grade_answer(question, selection, 100)
    assert error.value.status_code == 422
