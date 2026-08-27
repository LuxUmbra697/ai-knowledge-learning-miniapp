"""quiz_service 配图功能集成测试"""

from unittest.mock import AsyncMock, patch

import pytest

from app.models.quiz import QuizGenerateRequest, QuizOutput, Question, QuestionOption
from app.services import quiz_service


@pytest.fixture
def mock_quiz_output():
    return QuizOutput(
        title="英语单词闯关",
        summary="水果类单词",
        questions=[
            Question(
                id="q1",
                type="single",
                stem="苹果的英文是？",
                options=[
                    QuestionOption(key="A", text="apple"),
                    QuestionOption(key="B", text="banana"),
                    QuestionOption(key="C", text="orange"),
                    QuestionOption(key="D", text="grape"),
                ],
                answer=["A"],
                explanation="苹果的英文是 apple。",
                knowledge_point="水果单词",
                difficulty="easy",
            ),
            Question(
                id="q2",
                type="single",
                stem="香蕉的英文是？",
                options=[
                    QuestionOption(key="A", text="apple"),
                    QuestionOption(key="B", text="banana"),
                    QuestionOption(key="C", text="orange"),
                    QuestionOption(key="D", text="grape"),
                ],
                answer=["B"],
                explanation="香蕉的英文是 banana。",
                knowledge_point="水果单词",
                difficulty="easy",
            ),
        ],
    )


@pytest.mark.asyncio
class TestQuizGenerateWithImages:
    async def test_generate_images_false_skips_image_service(self, mock_quiz_output):
        """未勾选生成图片时，不应调用 image_service，questions 不带 image_url"""
        with patch(
            "app.services.quiz_service.fetch_knowledge_context",
            new_callable=AsyncMock,
            return_value="",
        ), patch(
            "app.services.quiz_service.generate_quiz",
            new_callable=AsyncMock,
            return_value=mock_quiz_output,
        ), patch(
            "app.services.quiz_service.check_content", return_value=True
        ), patch(
            "app.services.quiz_service.quiz_repository"
        ) as mock_repo, patch(
            "app.services.quiz_service.image_service.generate_images_for_quiz",
            new_callable=AsyncMock,
        ) as mock_image_gen:
            mock_repo.save_quiz_session = AsyncMock()

            req = QuizGenerateRequest(user_input="学习水果单词", question_count=3, generate_images=False)
            result = await quiz_service.handle_quiz_generate(req, user_id=1)

        mock_image_gen.assert_not_called()
        assert result.image_notice is None
        assert all(q.image_url is None for q in result.questions)

    async def test_generate_images_true_applies_urls_and_notice(self, mock_quiz_output):
        """勾选生成图片时，应调用 image_service 并将 url 写回题目、落库、透传 notice"""
        with patch(
            "app.services.quiz_service.fetch_knowledge_context",
            new_callable=AsyncMock,
            return_value="",
        ), patch(
            "app.services.quiz_service.generate_quiz",
            new_callable=AsyncMock,
            return_value=mock_quiz_output,
        ), patch(
            "app.services.quiz_service.check_content", return_value=True
        ), patch(
            "app.services.quiz_service.quiz_repository"
        ) as mock_repo, patch(
            "app.services.quiz_service.image_service.generate_images_for_quiz",
            new_callable=AsyncMock,
            return_value=({"q1": "https://cos.example.com/q1.png"}, "今日生图额度剩余 1 张，已为前 1 题生成配图，其余题目未配图"),
        ):
            mock_repo.save_quiz_session = AsyncMock()

            req = QuizGenerateRequest(user_input="学习水果单词", question_count=3, generate_images=True)
            result = await quiz_service.handle_quiz_generate(req, user_id=1)

        assert result.image_notice == "今日生图额度剩余 1 张，已为前 1 题生成配图，其余题目未配图"
        q1 = next(q for q in result.questions if q.id == "q1")
        q2 = next(q for q in result.questions if q.id == "q2")
        assert q1.image_url == "https://cos.example.com/q1.png"
        assert q2.image_url is None

        # 落库时应带上 image_url，供历史回看使用
        saved_questions = mock_repo.save_quiz_session.call_args.kwargs["questions_json"]
        saved_q1 = next(q for q in saved_questions if q["id"] == "q1")
        assert saved_q1["image_url"] == "https://cos.example.com/q1.png"

    async def test_image_service_exception_does_not_break_quiz_flow(self, mock_quiz_output):
        """image_service 内部意外抛出异常时，出题流程仍应正常返回（不带图片）"""
        with patch(
            "app.services.quiz_service.fetch_knowledge_context",
            new_callable=AsyncMock,
            return_value="",
        ), patch(
            "app.services.quiz_service.generate_quiz",
            new_callable=AsyncMock,
            return_value=mock_quiz_output,
        ), patch(
            "app.services.quiz_service.check_content", return_value=True
        ), patch(
            "app.services.quiz_service.quiz_repository"
        ) as mock_repo, patch(
            "app.services.quiz_service.image_service.generate_images_for_quiz",
            new_callable=AsyncMock,
            side_effect=RuntimeError("意外错误"),
        ):
            mock_repo.save_quiz_session = AsyncMock()

            req = QuizGenerateRequest(user_input="学习水果单词", question_count=3, generate_images=True)
            result = await quiz_service.handle_quiz_generate(req, user_id=1)

        assert result.title == "英语单词闯关"
        assert all(q.image_url is None for q in result.questions)
