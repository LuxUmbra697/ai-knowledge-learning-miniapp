"""出题链路集成测试 - 验证有/无搜索上下文时均能正常生成题目"""

from unittest.mock import AsyncMock, MagicMock, patch
import json

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
            "app.services.public_search_service.fetch_context",
            new_callable=AsyncMock,
            return_value="Harness 是一个持续交付平台...",
        ),
        patch(
            "app.services.quiz_task_service.generate_quiz",
            new_callable=AsyncMock,
            return_value=mock_quiz_output,
        ) as mock_gen,
        patch("app.services.quiz_service.check_content", return_value=True),
        patch("app.services.quiz_task_service.quiz_repository.publish_generated_quiz", new_callable=AsyncMock, return_value={'quiz_id': 'quiz_public'}) as publish,
    ):
        from types import SimpleNamespace
        from app.services.quiz_task_service import run
        context = SimpleNamespace(user_id=1, payload=dict(query='Harness Engineering', question_count=5, difficulty='mixed',
                                                         doc_ids=[], scope=[], use_web_search=True), checkpoints={}, checkpoint=AsyncMock())
        result = await run(context)
        assert result['quiz_id'] == 'quiz_public'
        publish.assert_awaited_once_with(context, mock_quiz_output)
        # 验证 search_context 被传递
        mock_gen.assert_called_once()
        call_kwargs = mock_gen.call_args
        assert call_kwargs.kwargs.get("search_context") == "Harness 是一个持续交付平台..."


@pytest.mark.asyncio
async def test_quiz_generate_without_search_context(mock_quiz_output):
    """Without consent, public generation does not contact search or private retrieval."""
    with (
        patch(
            "app.services.public_search_service.fetch_context",
            new_callable=AsyncMock,
            return_value="",
        ) as search,
        patch(
            "app.services.quiz_task_service.generate_quiz",
            new_callable=AsyncMock,
            return_value=mock_quiz_output,
        ) as mock_gen,
        patch("app.services.quiz_service.check_content", return_value=True),
        patch("app.services.quiz_task_service.quiz_repository.publish_generated_quiz", new_callable=AsyncMock, return_value={'quiz_id': 'quiz_public'}),
    ):
        from types import SimpleNamespace
        from app.services.quiz_task_service import run
        context = SimpleNamespace(user_id=1, payload=dict(query='Python 基础', question_count=5, difficulty='mixed', doc_ids=[], scope=[]),
                                  checkpoints={}, checkpoint=AsyncMock())
        result = await run(context)
        assert result['quiz_id'] == 'quiz_public'
        search.assert_not_awaited()
        call_kwargs = mock_gen.call_args
        assert call_kwargs.kwargs.get("search_context") == ""


@pytest.mark.asyncio
async def test_generate_quiz_passes_search_context_to_prompt(sample_quiz_response_data):
    """generate_quiz 应将 search_context 正确传入 prompt 模板"""
    mock_llm_response = MagicMock()
    # A prompt transport fixture must also satisfy the requested five-question contract.
    mock_llm_response.content = json.dumps({key: sample_quiz_response_data[key] for key in ('title', 'summary', 'questions')}, ensure_ascii=False)

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

        assert result.title == sample_quiz_response_data['title']
        assert len(result.questions) == 5
        # 验证 ainvoke 调用时传入了 search_context_section
        call_args = mock_chain.ainvoke.call_args
        invoke_dict = call_args[0][0] if call_args[0] else call_args.kwargs
        assert "search_context_section" in invoke_dict
        assert "Harness" in invoke_dict["search_context_section"]
