"""quiz_service doc_id（知识库出题）分支集成测试"""

from unittest.mock import AsyncMock, patch

import pytest

from app.core.exceptions import KnowledgeBaseError
from app.models.quiz import QuizGenerateRequest, QuizOutput, Question, QuestionOption
from app.services import quiz_service


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
class TestHandleQuizGenerateNoDocId:
    async def test_no_doc_id_uses_web_search_not_rag(self, mock_quiz_output):
        """无 doc_id 时应完全走原有联网搜索路径，不调用 rag_service，行为与之前一致"""
        with patch(
            "app.services.quiz_service.fetch_knowledge_context",
            new_callable=AsyncMock,
            return_value="联网搜索结果",
        ) as mock_web_search, patch(
            "app.services.quiz_service.rag_service.fetch_rag_context",
            new_callable=AsyncMock,
        ) as mock_rag, patch(
            "app.services.quiz_service.generate_quiz",
            new_callable=AsyncMock,
            return_value=mock_quiz_output,
        ), patch(
            "app.services.quiz_service.check_content", return_value=True
        ), patch(
            "app.services.quiz_service.quiz_repository"
        ) as mock_repo:
            mock_repo.save_quiz_session = AsyncMock()

            req = QuizGenerateRequest(user_input="学习 Python", question_count=5, difficulty="mixed")
            result = await quiz_service.handle_quiz_generate(req, user_id=1)

        assert result.title == "测试题库"
        mock_web_search.assert_called_once()
        mock_rag.assert_not_called()


@pytest.mark.asyncio
class TestHandleQuizGenerateWithDocId:
    async def test_valid_ready_doc_uses_rag_context(self, mock_quiz_output):
        """指定合法且已就绪的 doc_id 时，应调用 rag_service 而非联网搜索"""
        with patch(
            "app.services.quiz_service.knowledge_repository.get_document",
            new_callable=AsyncMock,
            return_value={"doc_id": "doc_1", "status": "ready"},
        ), patch(
            "app.services.quiz_service.rag_service.fetch_rag_context",
            new_callable=AsyncMock,
            return_value="知识库摘要内容",
        ) as mock_rag, patch(
            "app.services.quiz_service.fetch_knowledge_context",
            new_callable=AsyncMock,
        ) as mock_web_search, patch(
            "app.services.quiz_service.generate_quiz",
            new_callable=AsyncMock,
            return_value=mock_quiz_output,
        ) as mock_gen, patch(
            "app.services.quiz_service.check_content", return_value=True
        ), patch(
            "app.services.quiz_service.quiz_repository"
        ) as mock_repo:
            mock_repo.save_quiz_session = AsyncMock()

            req = QuizGenerateRequest(
                user_input="学习 Python", question_count=5, difficulty="mixed", doc_id="doc_1"
            )
            result = await quiz_service.handle_quiz_generate(req, user_id=1)

        assert result.title == "测试题库"
        mock_rag.assert_called_once_with("学习 Python", 1, "doc_1")
        mock_web_search.assert_not_called()
        assert mock_gen.call_args.kwargs.get("search_context") == "知识库摘要内容"

    async def test_doc_id_without_login_rejected(self):
        """未登录用户不能使用 doc_id 出题"""
        req = QuizGenerateRequest(
            user_input="学习 Python", question_count=5, difficulty="mixed", doc_id="doc_1"
        )
        with pytest.raises(KnowledgeBaseError, match="先登录"):
            await quiz_service.handle_quiz_generate(req, user_id=None)

    async def test_doc_id_not_found_rejected(self):
        """doc_id 不存在或不属于该用户时应拒绝"""
        with patch(
            "app.services.quiz_service.knowledge_repository.get_document",
            new_callable=AsyncMock,
            return_value=None,
        ):
            req = QuizGenerateRequest(
                user_input="学习 Python", question_count=5, difficulty="mixed", doc_id="doc_missing"
            )
            with pytest.raises(KnowledgeBaseError, match="不存在"):
                await quiz_service.handle_quiz_generate(req, user_id=1)

    async def test_doc_id_not_ready_rejected(self):
        """doc_id 状态非 ready（如 processing/failed）时应拒绝"""
        with patch(
            "app.services.quiz_service.knowledge_repository.get_document",
            new_callable=AsyncMock,
            return_value={"doc_id": "doc_1", "status": "processing"},
        ):
            req = QuizGenerateRequest(
                user_input="学习 Python", question_count=5, difficulty="mixed", doc_id="doc_1"
            )
            with pytest.raises(KnowledgeBaseError, match="尚未就绪"):
                await quiz_service.handle_quiz_generate(req, user_id=1)


@pytest.mark.asyncio
class TestCreateQuizTaskWithDocId:
    async def test_invalid_doc_id_rejected_before_task_created(self):
        """校验失败时不应创建任务记录，也不应启动后台任务"""
        with patch(
            "app.services.quiz_service.knowledge_repository.get_document",
            new_callable=AsyncMock,
            return_value=None,
        ), patch(
            "app.services.quiz_service.task_repository.create_task", new_callable=AsyncMock
        ) as mock_create_task, patch(
            "app.services.quiz_service.asyncio.create_task"
        ) as mock_asyncio_create_task, patch(
            "app.services.quiz_service.check_content", return_value=True
        ):
            req = QuizGenerateRequest(
                user_input="学习 Python", question_count=5, difficulty="mixed", doc_id="doc_missing"
            )
            with pytest.raises(KnowledgeBaseError):
                await quiz_service.create_quiz_task(req, user_id=1)

        mock_create_task.assert_not_called()
        mock_asyncio_create_task.assert_not_called()

    async def test_valid_doc_id_creates_task_and_runs_with_rag(self):
        """校验通过后应正常创建任务并在后台使用 rag_service 获取上下文"""
        with patch(
            "app.services.quiz_service.knowledge_repository.get_document",
            new_callable=AsyncMock,
            return_value={"doc_id": "doc_1", "status": "ready"},
        ), patch(
            "app.services.quiz_service.task_repository.create_task", new_callable=AsyncMock
        ) as mock_create_task, patch(
            "app.services.quiz_service.asyncio.create_task"
        ) as mock_asyncio_create_task, patch(
            "app.services.quiz_service.check_content", return_value=True
        ):
            req = QuizGenerateRequest(
                user_input="学习 Python", question_count=5, difficulty="mixed", doc_id="doc_1"
            )
            result = await quiz_service.create_quiz_task(req, user_id=1)

        assert result.task_id.startswith("task_")
        mock_create_task.assert_called_once()
        mock_asyncio_create_task.assert_called_once()
        # 关闭未被真正调度的协程，避免 "never awaited" 警告
        mock_asyncio_create_task.call_args[0][0].close()
