"""用户系统 API 集成测试"""

from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.auth import create_token
from app.main import app


@pytest.fixture
def auth_header():
    """生成一个有效的 JWT token 用于测试。"""
    token = create_token(user_id=1, openid="test_openid_123")
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
class TestLoginAPI:
    async def test_login_success(self):
        """模拟微信登录成功"""
        mock_user = {
            "id": 1,
            "openid": "mock_openid",
            "nickname": "学习者",
            "avatar_url": "",
            "total_xp": 0,
        }

        with patch(
            "app.services.user_service.wx_code_to_openid",
            new_callable=AsyncMock,
            return_value="mock_openid",
        ), patch(
            "app.services.user_service.user_repository.find_user_by_openid",
            new_callable=AsyncMock,
            return_value=None,
        ), patch(
            "app.services.user_service.user_repository.create_user",
            new_callable=AsyncMock,
            return_value=mock_user,
        ):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post(
                    "/api/v1/user/login",
                    json={"code": "mock_wx_code"},
                )
            assert resp.status_code == 200
            body = resp.json()
            assert body["code"] == 0
            assert "token" in body["data"]
            assert body["data"]["user"]["nickname"] == "学习者"

    async def test_login_existing_user(self):
        """已注册用户登录"""
        mock_user = {
            "id": 5,
            "openid": "existing_openid",
            "nickname": "LuxUmbra同学",
            "avatar_url": "https://example.com/avatar.png",
            "total_xp": 100,
        }

        with patch(
            "app.services.user_service.wx_code_to_openid",
            new_callable=AsyncMock,
            return_value="existing_openid",
        ), patch(
            "app.services.user_service.user_repository.find_user_by_openid",
            new_callable=AsyncMock,
            return_value=mock_user,
        ):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post(
                    "/api/v1/user/login",
                    json={"code": "mock_wx_code"},
                )
            assert resp.status_code == 200
            body = resp.json()
            assert body["data"]["user"]["id"] == 5
            assert body["data"]["user"]["total_xp"] == 100

    async def test_login_empty_code_rejected(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post("/api/v1/user/login", json={"code": ""})
        assert resp.status_code == 422


@pytest.mark.asyncio
class TestProfileAPI:
    async def test_get_profile_success(self, auth_header):
        mock_user = {
            "id": 1,
            "openid": "test_openid_123",
            "nickname": "测试用户",
            "avatar_url": "",
            "total_xp": 18,
        }

        with patch(
            "app.services.user_service.user_repository.get_user_by_id",
            new_callable=AsyncMock,
            return_value=mock_user,
        ), patch(
            "app.services.user_service.quiz_repository.get_user_quiz_count",
            new_callable=AsyncMock,
            return_value=3,
        ), patch(
            "app.services.user_service.quiz_repository.get_user_answer_stats",
            new_callable=AsyncMock,
            return_value={"correct_count": 12, "average_accuracy": 80},
        ):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.get("/api/v1/user/profile", headers=auth_header)
            assert resp.status_code == 200
            body = resp.json()
            assert body["code"] == 0
            assert body["data"]["quiz_count"] == 3
            assert body["data"]["correct_count"] == 12
            assert body["data"]["average_accuracy"] == 80

    async def test_get_profile_unauthorized(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/v1/user/profile")
        assert resp.status_code == 401

    async def test_update_profile_success(self, auth_header):
        with patch(
            "app.services.user_service.user_repository.update_user_profile",
            new_callable=AsyncMock,
        ) as mock_update:
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.put(
                    "/api/v1/user/profile",
                    json={"nickname": "新昵称"},
                    headers=auth_header,
                )
            assert resp.status_code == 200
            mock_update.assert_called_once_with(1, "新昵称", None)


@pytest.mark.asyncio
class TestQuizHistoryAPI:
    async def test_get_quiz_list(self, auth_header):
        mock_items = [
            {
                "quiz_id": "quiz_abc123",
                "title": "RAG 入门闯关",
                "accuracy": 80.0,
                "question_count": 5,
                "created_at": "2026-04-08 10:00:00",
            }
        ]

        with patch(
            "app.services.history_service.quiz_repository.get_user_quiz_list",
            new_callable=AsyncMock,
            return_value=(mock_items, 1),
        ):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.get(
                    "/api/v1/user/quizzes?page=1&page_size=10",
                    headers=auth_header,
                )
            assert resp.status_code == 200
            body = resp.json()
            assert body["code"] == 0
            assert len(body["data"]["items"]) == 1
            assert body["data"]["total"] == 1

    async def test_get_quiz_list_unauthorized(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/v1/user/quizzes")
        assert resp.status_code == 401

    async def test_get_quiz_detail(self, auth_header):
        mock_detail = {
            "quiz_id": "quiz_abc123",
            "title": "RAG 入门",
            "summary": "测试摘要",
            "user_input": "RAG",
            "questions": [{"id": "q1", "stem": "test"}],
            "answer_records": [{"question_id": "q1", "is_correct": True}],
            "report": {"accuracy": 100},
            "created_at": "2026-04-08 10:00:00",
        }

        with patch(
            "app.services.history_service.quiz_repository.get_quiz_detail",
            new_callable=AsyncMock,
            return_value=mock_detail,
        ):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.get(
                    "/api/v1/user/quizzes/quiz_abc123",
                    headers=auth_header,
                )
            assert resp.status_code == 200
            body = resp.json()
            assert body["code"] == 0
            assert body["data"]["quiz_id"] == "quiz_abc123"

    async def test_get_quiz_detail_not_found(self, auth_header):
        with patch(
            "app.services.history_service.quiz_repository.get_quiz_detail",
            new_callable=AsyncMock,
            return_value=None,
        ):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.get(
                    "/api/v1/user/quizzes/quiz_nonexist",
                    headers=auth_header,
                )
            assert resp.status_code == 404
            body = resp.json()
            assert body["code"] == 4004
            assert body["data"] is None


@pytest.mark.asyncio
class TestQuizAuthentication:
    """Costly generation requires a verified identity."""

    async def test_quiz_generate_without_token(self):
        """Anonymous requests must not invoke a paid model."""
        from app.models.quiz import QuizOutput, Question, QuestionOption

        mock_output = QuizOutput(
            title="Test",
            summary="Test summary",
            questions=[
                Question(
                    id="q1", type="single", stem="test?",
                    options=[
                        QuestionOption(key="A", text="a"),
                        QuestionOption(key="B", text="b"),
                    ],
                    answer=["A"], explanation="test", knowledge_point="test", difficulty="easy",
                ),
            ],
        )
        with patch(
            "app.services.quiz_service.generate_quiz",
            new_callable=AsyncMock,
            return_value=mock_output,
        ) as model:
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post(
                    "/api/v1/quiz/generate",
                    json={"user_input": "Python basic", "question_count": 3, "difficulty": "easy"},
                )
            assert resp.status_code == 401
            model.assert_not_awaited()

    async def test_quiz_generate_with_token(self, auth_header, durable_quiz_transport):
        """有 token 时应正常工作且落库"""
        from app.models.quiz import QuizOutput, Question, QuestionOption

        mock_output = QuizOutput(
            title="Test",
            summary="Test summary",
            questions=[
                Question(
                    id="q1", type="single", stem="test?",
                    options=[
                        QuestionOption(key="A", text="a"),
                        QuestionOption(key="B", text="b"),
                    ],
                    answer=["A"], explanation="test", knowledge_point="test", difficulty="easy",
                ),
            ],
        )
        queue = durable_quiz_transport(mock_output)
        with patch(
            "app.services.quiz_service.generate_quiz",
            new_callable=AsyncMock,
            return_value=mock_output,
        ), patch(
            "app.services.quiz_service.quiz_repository.save_quiz_session",
            new_callable=AsyncMock,
        ) as mock_save:
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post(
                    "/api/v1/quiz/generate",
                    json={"user_input": "Python basic", "question_count": 3, "difficulty": "easy"},
                    headers=auth_header,
                )
            assert resp.status_code == 200
            queue.create.assert_awaited_once()
            assert queue.create.await_args.args[1] == 1
            queue.wait.assert_awaited_once_with('job_' + 'a' * 32, 1, seconds=60)
            mock_save.assert_not_awaited()


@pytest.mark.asyncio
class TestReportAuthenticatedQueue:
    """报告路由把认证身份传递给持久化任务，模型只在 worker 执行。"""

    async def test_report_generate_with_token_queues_owned_data(self, auth_header, sample_report_request):
        from app.models.report import ReportOutput

        mock_output = ReportOutput(
            accuracy=80,
            mastered_points=["point1"],
            weak_points=["point2"],
            three_line_summary=["s1", "s2", "s3"],
            advice=["a1"],
            share_quote="quote",
        )
        with patch(
            "app.services.report_service.wait_result",
            new_callable=AsyncMock,
            return_value=mock_output.model_dump(),
        ), patch("app.services.report_service.quiz_repository.get_quiz_detail", new_callable=AsyncMock,
                 return_value={"title": sample_report_request["topic"], "questions": sample_report_request["questions"]}), \
             patch("app.services.report_service.get_attempts", new_callable=AsyncMock,
                   return_value=sample_report_request["answer_records"]), \
             patch("app.services.report_service.jobs.enqueue", new_callable=AsyncMock,
                   return_value={'task_id': 'job_mock'}) as enqueue:
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post(
                    "/api/v1/report/generate",
                    json=sample_report_request,
                    headers=auth_header,
                )
            assert resp.status_code == 200
            enqueue.assert_awaited_once()
            assert enqueue.call_args.args[:2] == (1, 'report')
            assert enqueue.call_args.args[2]['quiz_id'] == sample_report_request['quiz_id']
            assert resp.json()["data"]["accuracy"] == 80
