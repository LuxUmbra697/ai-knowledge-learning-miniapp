"""出题链路集成测试 - 验证有/无搜索上下文时均能正常生成题目"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.quiz import QuizOutput, Question, QuestionOption


@pytest.fixture
def mock_quiz_output():
    return QuizOutput(
        title="测试题库",
        summary="测试摘要",
        questions=[
            Question(
                id="q1",
                type="single",
                stem="测试题干",
                options=[
                    QuestionOption(key="A", text="选项A"),
                    QuestionOption(key="B", text="选项B"),
                    QuestionOption(key="C", text="选项C"),
                    QuestionOption(key="D", text="选项D"),
                ],
                answer=["A"],
                explanation="测试讲解",
                knowledge_point="测试知识点",
                difficulty="easy",
            )
        ],
    )


@pytest.mark.asyncio
async def test_quiz_generate_with_search_context(mock_quiz_output):
    """有搜索上下文时正常生成题目"""
    with (
        patch(
            "app.services.quiz_service.fetch_knowledge_context",
            new_callable=AsyncMock,
            return_value="Harness 是一个持续交付平台...",
        ),
        patch(
            "app.services.quiz_service.generate_quiz",
            new_callable=AsyncMock,
            return_value=mock_quiz_output,
        ) as mock_gen,
        patch("app.services.quiz_service.check_content", return_value=True),
        patch("app.services.quiz_service.quiz_repository") as mock_repo,
    ):
        mock_repo.save_quiz_session = AsyncMock()

        from app.models.quiz import QuizGenerateRequest
        from app.services.quiz_service import handle_quiz_generate

        req = QuizGenerateRequest(
            user_input="Harness Engineering",
            question_count=5,
            difficulty="mixed",
        )
        result = await handle_quiz_generate(req)

        assert result.title == "测试题库"
        # 验证 search_context 被传递
        mock_gen.assert_called_once()
        call_kwargs = mock_gen.call_args
        assert call_kwargs.kwargs.get("search_context") == "Harness 是一个持续交付平台..."


@pytest.mark.asyncio
async def test_quiz_generate_without_search_context(mock_quiz_output):
    """搜索返回空时仍正常生成题目"""
    with (
        patch(
            "app.services.quiz_service.fetch_knowledge_context",
            new_callable=AsyncMock,
            return_value="",
        ),
        patch(
            "app.services.quiz_service.generate_quiz",
            new_callable=AsyncMock,
            return_value=mock_quiz_output,
        ) as mock_gen,
        patch("app.services.quiz_service.check_content", return_value=True),
        patch("app.services.quiz_service.quiz_repository") as mock_repo,
    ):
        mock_repo.save_quiz_session = AsyncMock()

        from app.models.quiz import QuizGenerateRequest
        from app.services.quiz_service import handle_quiz_generate

        req = QuizGenerateRequest(
            user_input="Python 基础",
            question_count=5,
            difficulty="mixed",
        )
        result = await handle_quiz_generate(req)

        assert result.title == "测试题库"
        call_kwargs = mock_gen.call_args
        assert call_kwargs.kwargs.get("search_context") == ""


@pytest.mark.asyncio
async def test_generate_quiz_passes_search_context_to_prompt():
    """generate_quiz 应将 search_context 正确传入 prompt 模板"""
    mock_llm_response = MagicMock()
    mock_llm_response.content = '''{
        "title": "测试",
        "summary": "测试摘要",
        "questions": [{
            "id": "q1", "type": "single", "stem": "题干",
            "options": [{"key": "A", "text": "A"}, {"key": "B", "text": "B"},
                        {"key": "C", "text": "C"}, {"key": "D", "text": "D"}],
            "answer": ["A"], "explanation": "讲解",
            "knowledge_point": "知识点", "difficulty": "easy"
        }]
    }'''

    mock_chain = MagicMock()
    mock_chain.ainvoke = AsyncMock(return_value=mock_llm_response)

    with (
        patch("app.llm.quiz_chain.get_chat_model") as mock_get_model,
        patch("app.llm.quiz_chain.ChatPromptTemplate") as mock_prompt_cls,
    ):
        mock_prompt = MagicMock()
        mock_prompt_cls.from_messages.return_value = mock_prompt
        # prompt | llm 返回 mock_chain
        mock_prompt.__or__ = MagicMock(return_value=mock_chain)

        mock_get_model.return_value = MagicMock()

        from app.llm.quiz_chain import generate_quiz

        result = await generate_quiz(
            user_input="Harness",
            search_context="Harness 是一个 CD 平台",
        )

        assert result.title == "测试"
        # 验证 ainvoke 调用时传入了 search_context_section
        call_args = mock_chain.ainvoke.call_args
        invoke_dict = call_args[0][0] if call_args[0] else call_args.kwargs
        assert "search_context_section" in invoke_dict
        assert "Harness" in invoke_dict["search_context_section"]
