"""quiz_service doc_id（知识库出题）分支集成测试"""

from unittest.mock import AsyncMock, patch

import pytest

from fastapi import HTTPException
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
    async def test_valid_ready_doc_waits_for_durable_private_result(self, mock_quiz_output):
        """The sync compatibility endpoint waits for the owned job, never its own model call."""
        with patch('app.services.quiz_task_service.create', new_callable=AsyncMock,
                   return_value={'task_id': 'job_fixture'}) as create, patch(
            'app.services.learning_task_service.wait_result', new_callable=AsyncMock,
            return_value={'quiz_id': 'quiz_fixture'}) as wait, patch(
            'app.services.quiz_task_service.result_response', new_callable=AsyncMock,
            return_value=mock_quiz_output) as restore, patch(
            "app.services.quiz_service.fetch_knowledge_context",
            new_callable=AsyncMock,
        ) as mock_web_search, patch(
            "app.services.quiz_service.generate_quiz",
            new_callable=AsyncMock,
        ) as mock_gen:
            req = QuizGenerateRequest(
                user_input="学习 Python", question_count=5, difficulty="mixed", doc_id="doc_1"
            )
            result = await quiz_service.handle_quiz_generate(req, user_id=1)

        assert result.title == "测试题库"
        create.assert_awaited_once_with(req, 1, None)
        wait.assert_awaited_once_with('job_fixture', 1, seconds=60)
        restore.assert_awaited_once_with({'quiz_id': 'quiz_fixture'}, 1)
        mock_web_search.assert_not_called()
        mock_gen.assert_not_called()

    async def test_doc_id_without_login_rejected(self):
        """未登录用户不能使用 doc_id 出题"""
        req = QuizGenerateRequest(
            user_input="学习 Python", question_count=5, difficulty="mixed", doc_id="doc_1"
        )
        with pytest.raises(HTTPException) as error:
            await quiz_service.handle_quiz_generate(req, user_id=None)
        assert error.value.status_code == 401

    async def test_doc_id_not_found_rejected(self):
        """doc_id 不存在或不属于该用户时应拒绝"""
        with patch(
            "app.services.quiz_task_service.index.scoped_chunks",
            new_callable=AsyncMock,
            side_effect=HTTPException(404, '文档不存在'),
        ):
            req = QuizGenerateRequest(
                user_input="学习 Python", question_count=5, difficulty="mixed", doc_id="doc_missing"
            )
            with pytest.raises(HTTPException) as error:
                await quiz_service.handle_quiz_generate(req, user_id=1)
            assert error.value.status_code == 404

    async def test_doc_id_not_ready_rejected(self):
        """doc_id 状态非 ready（如 processing/failed）时应拒绝"""
        with patch(
            "app.services.quiz_task_service.index.scoped_chunks",
            new_callable=AsyncMock,
            side_effect=HTTPException(409, '文档尚未就绪'),
        ):
            req = QuizGenerateRequest(
                user_input="学习 Python", question_count=5, difficulty="mixed", doc_id="doc_1"
            )
            with pytest.raises(HTTPException) as error:
                await quiz_service.handle_quiz_generate(req, user_id=1)
            assert error.value.status_code == 409


@pytest.mark.asyncio
class TestCreateQuizTaskWithDocId:
    async def test_invalid_doc_id_rejected_before_task_created(self):
        """校验失败时不应创建任务记录，也不应启动后台任务"""
        with patch(
            "app.services.quiz_task_service.index.scoped_chunks",
            new_callable=AsyncMock,
            side_effect=HTTPException(404, '文档不存在'),
        ), patch(
            "app.services.quiz_task_service.jobs.enqueue", new_callable=AsyncMock
        ) as mock_create_task, patch(
            "app.services.quiz_service.asyncio.create_task"
        ) as mock_asyncio_create_task, patch(
            "app.services.quiz_service.check_content", return_value=True
        ):
            req = QuizGenerateRequest(
                user_input="学习 Python", question_count=5, difficulty="mixed", doc_id="doc_missing"
            )
            with pytest.raises(HTTPException) as error:
                await quiz_service.create_quiz_task(req, user_id=1)
            assert error.value.status_code == 404

        mock_create_task.assert_not_called()
        mock_asyncio_create_task.assert_not_called()

    async def test_valid_doc_id_enqueues_without_process_local_task(self):
        """Admission persists the owned revision and does not schedule a process-local task."""
        with patch(
            "app.services.quiz_task_service.index.scoped_chunks",
            new_callable=AsyncMock,
            return_value=[{"doc_id": "doc_1", "revision": 1, "index_version": "v1"}],
        ), patch(
            "app.services.quiz_task_service.jobs.enqueue", new_callable=AsyncMock, return_value={'task_id': 'job_fixture'}
        ) as mock_create_task, patch(
            "app.services.quiz_service.asyncio.create_task"
        ) as mock_asyncio_create_task, patch(
            "app.services.quiz_service.check_content", return_value=True
        ):
            req = QuizGenerateRequest(
                user_input="学习 Python", question_count=5, difficulty="mixed", doc_id="doc_1"
            )
            result = await quiz_service.create_quiz_task(req, user_id=1)

        assert result.task_id.startswith("job_")
        mock_create_task.assert_awaited_once()
        assert mock_create_task.await_args.args[:2] == (1, 'quiz')
        assert mock_create_task.await_args.args[2]['scope'] == [['doc_1', 1, 'v1']]
        mock_asyncio_create_task.assert_not_called()
