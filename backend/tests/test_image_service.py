"""题目配图生成服务单元测试"""

from unittest.mock import AsyncMock, patch

import pytest

from app.models.quiz import Question, QuestionOption
from app.services import image_service


def _make_question(qid: str) -> Question:
    return Question(
        id=qid,
        type="single",
        stem=f"苹果的英文单词是什么？（{qid}）",
        options=[
            QuestionOption(key="A", text="apple"),
            QuestionOption(key="B", text="banana"),
            QuestionOption(key="C", text="orange"),
            QuestionOption(key="D", text="grape"),
        ],
        answer=["A"],
        explanation="苹果的英文是 apple。",
        knowledge_point="英语单词-水果",
        difficulty="easy",
    )


class TestBuildImagePrompt:
    def test_prompt_contains_stem_and_knowledge_point(self):
        question = _make_question("q1")
        prompt = image_service.build_image_prompt(question)

        assert question.stem in prompt
        assert question.knowledge_point in prompt
        assert "文字" in prompt  # 要求画面不含文字/答案


class TestDeriveImageBaseUrl:
    def test_replaces_compatible_mode_suffix(self):
        result = image_service._derive_image_base_url(
            "https://xxx.cn-beijing.maas.aliyuncs.com/compatible-mode/v1"
        )
        assert result == "https://xxx.cn-beijing.maas.aliyuncs.com/api/v1"

    def test_leaves_other_urls_unchanged(self):
        result = image_service._derive_image_base_url("https://dashscope.aliyuncs.com/api/v1")
        assert result == "https://dashscope.aliyuncs.com/api/v1"


@pytest.mark.asyncio
class TestGenerateImagesForQuiz:
    async def test_anonymous_user_skips_generation(self):
        questions = [_make_question("q1"), _make_question("q2")]

        image_map, notice = await image_service.generate_images_for_quiz(
            questions, user_id=None, quiz_id="quiz_1"
        )

        assert image_map == {}
        assert "登录" in notice

    async def test_quota_exhausted_skips_all(self):
        questions = [_make_question("q1"), _make_question("q2")]

        with patch(
            "app.services.image_service.image_repository.get_today_usage_count",
            new_callable=AsyncMock,
            return_value=20,
        ), patch(
            "app.services.image_service.generate_image_for_question",
            new_callable=AsyncMock,
        ) as mock_gen:
            image_map, notice = await image_service.generate_images_for_quiz(
                questions, user_id=1, quiz_id="quiz_1"
            )

        assert image_map == {}
        assert "已用完" in notice
        mock_gen.assert_not_called()

    async def test_partial_quota_only_generates_for_remaining(self):
        questions = [_make_question("q1"), _make_question("q2"), _make_question("q3")]

        with patch(
            "app.services.image_service.image_repository.get_today_usage_count",
            new_callable=AsyncMock,
            return_value=19,
        ), patch(
            "app.services.image_service.image_repository.log_image_generation",
            new_callable=AsyncMock,
        ), patch(
            "app.services.image_service.generate_image_for_question",
            new_callable=AsyncMock,
            return_value="https://example.com/img.png",
        ) as mock_gen:
            image_map, notice = await image_service.generate_images_for_quiz(
                questions, user_id=1, quiz_id="quiz_1"
            )

        assert len(image_map) == 1
        assert image_map["q1"] == "https://example.com/img.png"
        assert "剩余 1 张" in notice
        assert mock_gen.call_count == 1

    async def test_full_quota_generates_all_concurrently(self):
        questions = [_make_question("q1"), _make_question("q2")]

        async def fake_generate(question, quiz_id):
            return f"https://example.com/{question.id}.png"

        with patch(
            "app.services.image_service.image_repository.get_today_usage_count",
            new_callable=AsyncMock,
            return_value=0,
        ), patch(
            "app.services.image_service.image_repository.log_image_generation",
            new_callable=AsyncMock,
        ) as mock_log, patch(
            "app.services.image_service.generate_image_for_question",
            side_effect=fake_generate,
        ):
            image_map, notice = await image_service.generate_images_for_quiz(
                questions, user_id=1, quiz_id="quiz_1"
            )

        assert image_map == {
            "q1": "https://example.com/q1.png",
            "q2": "https://example.com/q2.png",
        }
        assert notice is None
        assert mock_log.call_count == 2

    async def test_individual_failure_does_not_affect_others(self):
        """某道题生图失败（返回 None）不影响其他题目正常拿到图片，也不抛异常"""
        questions = [_make_question("q1"), _make_question("q2")]

        async def fake_generate(question, quiz_id):
            if question.id == "q1":
                return None
            return "https://example.com/q2.png"

        with patch(
            "app.services.image_service.image_repository.get_today_usage_count",
            new_callable=AsyncMock,
            return_value=0,
        ), patch(
            "app.services.image_service.image_repository.log_image_generation",
            new_callable=AsyncMock,
        ), patch(
            "app.services.image_service.generate_image_for_question",
            side_effect=fake_generate,
        ):
            image_map, notice = await image_service.generate_images_for_quiz(
                questions, user_id=1, quiz_id="quiz_1"
            )

        assert image_map == {"q2": "https://example.com/q2.png"}


@pytest.mark.asyncio
class TestGenerateImageForQuestion:
    async def test_model_call_failure_returns_none(self):
        """生图模型调用失败时应返回 None 而不是抛异常"""
        question = _make_question("q1")

        with patch(
            "app.services.image_service.asyncio.to_thread",
            new_callable=AsyncMock,
            side_effect=RuntimeError("生图失败：InvalidParameter xxx"),
        ):
            result = await image_service.generate_image_for_question(question, "quiz_1")

        assert result is None

    async def test_download_failure_returns_none(self):
        """图片下载失败时应返回 None 而不是抛异常"""
        question = _make_question("q1")

        with patch(
            "app.services.image_service.asyncio.to_thread",
            new_callable=AsyncMock,
            return_value="https://temp.example.com/img.png",
        ), patch(
            "app.services.image_service._download_image",
            new_callable=AsyncMock,
            side_effect=RuntimeError("下载失败"),
        ):
            result = await image_service.generate_image_for_question(question, "quiz_1")

        assert result is None

    async def test_cos_upload_failure_returns_none(self):
        """COS 上传失败时应返回 None 而不是抛异常"""
        question = _make_question("q1")

        with patch(
            "app.services.image_service.asyncio.to_thread",
            new_callable=AsyncMock,
            return_value="https://temp.example.com/img.png",
        ), patch(
            "app.services.image_service._download_image",
            new_callable=AsyncMock,
            return_value=b"fake-bytes",
        ), patch(
            "app.services.image_service.upload_image_bytes",
            new_callable=AsyncMock,
            side_effect=RuntimeError("COS 上传失败"),
        ):
            result = await image_service.generate_image_for_question(question, "quiz_1")

        assert result is None

    async def test_success_returns_cos_url(self):
        question = _make_question("q1")

        with patch(
            "app.services.image_service.asyncio.to_thread",
            new_callable=AsyncMock,
            return_value="https://temp.example.com/img.png",
        ), patch(
            "app.services.image_service._download_image",
            new_callable=AsyncMock,
            return_value=b"fake-bytes",
        ), patch(
            "app.services.image_service.upload_image_bytes",
            new_callable=AsyncMock,
            return_value="https://cos.example.com/quiz-images/quiz_1/q1.png",
        ):
            result = await image_service.generate_image_for_question(question, "quiz_1")

        assert result == "https://cos.example.com/quiz-images/quiz_1/q1.png"
