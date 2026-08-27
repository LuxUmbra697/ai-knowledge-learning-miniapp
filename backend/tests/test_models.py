"""模型单元测试"""

import pytest
from pydantic import ValidationError

from app.models.quiz import (
    QuizGenerateRequest,
    QuizOutput,
    Question,
    QuestionOption,
    AnswerRecord,
)
from app.models.report import ReportGenerateRequest, ReportOutput, ReportGenerateResponse
from app.models.common import ApiResponse


class TestQuizGenerateRequest:
    def test_valid_request(self):
        req = QuizGenerateRequest(user_input="学习 Python 基础")
        assert req.user_input == "学习 Python 基础"
        assert req.question_count == 5
        assert req.difficulty == "mixed"

    def test_empty_input_rejected(self):
        with pytest.raises(ValidationError):
            QuizGenerateRequest(user_input="")

    def test_too_long_input_rejected(self):
        with pytest.raises(ValidationError):
            QuizGenerateRequest(user_input="x" * 2001)

    def test_question_count_bounds(self):
        with pytest.raises(ValidationError):
            QuizGenerateRequest(user_input="test", question_count=2)
        with pytest.raises(ValidationError):
            QuizGenerateRequest(user_input="test", question_count=11)

    def test_invalid_difficulty_rejected(self):
        with pytest.raises(ValidationError):
            QuizGenerateRequest(user_input="test", difficulty="impossible")


class TestQuizOutput:
    def test_valid_output(self, sample_quiz_response_data):
        output = QuizOutput(
            title=sample_quiz_response_data["title"],
            summary=sample_quiz_response_data["summary"],
            questions=sample_quiz_response_data["questions"],
        )
        assert len(output.questions) == 5
        assert output.questions[0].type == "single"
        assert output.questions[3].type == "multiple"
        assert output.questions[4].type == "judge"

    def test_question_option_structure(self):
        opt = QuestionOption(key="A", text="选项A")
        assert opt.key == "A"
        assert opt.text == "选项A"


class TestAnswerRecord:
    def test_valid_record(self):
        record = AnswerRecord(
            question_id="q1",
            selected_answers=["A"],
            is_correct=True,
            duration_ms=3200,
        )
        assert record.is_correct is True

    def test_negative_duration_rejected(self):
        with pytest.raises(ValidationError):
            AnswerRecord(
                question_id="q1",
                selected_answers=["A"],
                is_correct=True,
                duration_ms=-1,
            )


class TestReportOutput:
    def test_valid_output(self):
        output = ReportOutput(
            accuracy=80,
            mastered_points=["知识点1"],
            weak_points=["知识点2"],
            three_line_summary=["句子1", "句子2", "句子3"],
            advice=["建议1"],
            share_quote="学无止境",
        )
        assert output.accuracy == 80
        assert len(output.three_line_summary) == 3


class TestApiResponse:
    def test_success(self):
        resp = ApiResponse.success(data={"foo": "bar"})
        assert resp.code == 0
        assert resp.message == "ok"
        assert resp.data == {"foo": "bar"}

    def test_error(self):
        resp = ApiResponse.error(code=5001, message="生成失败")
        assert resp.code == 5001
        assert resp.data is None
