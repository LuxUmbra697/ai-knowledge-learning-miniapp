"""Prompt 契约测试 - 验证 Prompt 模板变量完整"""

from app.prompts.quiz_prompt import QUIZ_HUMAN_PROMPT
from app.prompts.report_prompt import REPORT_HUMAN_PROMPT


class TestPromptContract:
    def test_quiz_prompt_has_all_placeholders(self):
        assert "{user_input}" in QUIZ_HUMAN_PROMPT
        assert "{question_count}" in QUIZ_HUMAN_PROMPT
        assert "{difficulty}" in QUIZ_HUMAN_PROMPT

    def test_report_prompt_has_all_placeholders(self):
        assert "{topic}" in REPORT_HUMAN_PROMPT
        assert "{quiz_json}" in REPORT_HUMAN_PROMPT
        assert "{answer_records}" in REPORT_HUMAN_PROMPT
        assert "{score_summary}" in REPORT_HUMAN_PROMPT

    def test_quiz_prompt_formattable(self):
        result = QUIZ_HUMAN_PROMPT.format(
            user_input="test", question_count=5, difficulty="mixed",
            search_context_section="",
        )
        assert "test" in result
        assert "5" in result

    def test_report_prompt_formattable(self):
        result = REPORT_HUMAN_PROMPT.format(
            topic="test",
            quiz_json="[]",
            answer_records="[]",
            score_summary="{}",
        )
        assert "test" in result
