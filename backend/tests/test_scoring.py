"""计分服务测试"""

from app.models.quiz import AnswerRecord
from app.services.scoring_service import compute_score_summary


class TestScoringService:
    def test_all_correct(self):
        records = [
            AnswerRecord(question_id="q1", selected_answers=["A"], is_correct=True, duration_ms=3000),
            AnswerRecord(question_id="q2", selected_answers=["B"], is_correct=True, duration_ms=4000),
        ]
        result = compute_score_summary(records)
        assert result["total"] == 2
        assert result["correct"] == 2
        assert result["wrong"] == 0
        assert result["accuracy"] == 100

    def test_partial_correct(self):
        records = [
            AnswerRecord(question_id="q1", selected_answers=["A"], is_correct=True, duration_ms=3000),
            AnswerRecord(question_id="q2", selected_answers=["C"], is_correct=False, duration_ms=5000),
            AnswerRecord(question_id="q3", selected_answers=["A"], is_correct=False, duration_ms=4000),
            AnswerRecord(question_id="q4", selected_answers=["B"], is_correct=True, duration_ms=2000),
            AnswerRecord(question_id="q5", selected_answers=["A"], is_correct=False, duration_ms=6000),
        ]
        result = compute_score_summary(records)
        assert result["total"] == 5
        assert result["correct"] == 2
        assert result["wrong"] == 3
        assert result["accuracy"] == 40
        assert result["avg_duration_ms"] == 4000

    def test_empty_records(self):
        result = compute_score_summary([])
        assert result["total"] == 0
        assert result["accuracy"] == 0
        assert result["avg_duration_ms"] == 0
