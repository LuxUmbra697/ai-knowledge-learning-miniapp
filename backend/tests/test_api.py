"""API 集成测试（使用 mock LLM）"""

from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.models.quiz import QuizOutput, Question, QuestionOption
from app.models.report import ReportOutput
from app.core.auth import create_token


@pytest.fixture
def authenticated_headers():
    return {"Authorization": "Bearer " + create_token(1, "test-user")}


@pytest.fixture
def mock_quiz_output():
    return QuizOutput(
        title="Python 基础闯关",
        summary="围绕 Python 基础语法生成的题库",
        questions=[
            Question(
                id="q1",
                type="single",
                stem="Python 中用什么关键字定义函数？",
                options=[
                    QuestionOption(key="A", text="def"),
                    QuestionOption(key="B", text="func"),
                    QuestionOption(key="C", text="function"),
                    QuestionOption(key="D", text="define"),
                ],
                answer=["A"],
                explanation="Python 使用 def 关键字定义函数。",
                knowledge_point="函数定义",
                difficulty="easy",
            ),
            Question(
                id="q2",
                type="single",
                stem="Python 列表用什么符号？",
                options=[
                    QuestionOption(key="A", text="()"),
                    QuestionOption(key="B", text="[]"),
                    QuestionOption(key="C", text="{}"),
                    QuestionOption(key="D", text="<>"),
                ],
                answer=["B"],
                explanation="Python 列表使用方括号 []。",
                knowledge_point="数据类型",
                difficulty="easy",
            ),
            Question(
                id="q3",
                type="single",
                stem="以下哪个不是 Python 数据类型？",
                options=[
                    QuestionOption(key="A", text="int"),
                    QuestionOption(key="B", text="str"),
                    QuestionOption(key="C", text="char"),
                    QuestionOption(key="D", text="float"),
                ],
                answer=["C"],
                explanation="Python 没有 char 类型。",
                knowledge_point="数据类型",
                difficulty="easy",
            ),
            Question(
                id="q4",
                type="multiple",
                stem="以下哪些是 Python 的内置数据结构？",
                options=[
                    QuestionOption(key="A", text="list"),
                    QuestionOption(key="B", text="dict"),
                    QuestionOption(key="C", text="array"),
                    QuestionOption(key="D", text="tuple"),
                ],
                answer=["A", "B", "D"],
                explanation="list、dict、tuple 都是内置数据结构，array 需要导入。",
                knowledge_point="数据结构",
                difficulty="medium",
            ),
            Question(
                id="q5",
                type="judge",
                stem="Python 是编译型语言。",
                options=[
                    QuestionOption(key="A", text="正确"),
                    QuestionOption(key="B", text="错误"),
                ],
                answer=["B"],
                explanation="Python 是解释型语言。",
                knowledge_point="语言特性",
                difficulty="easy",
            ),
        ],
    )


@pytest.fixture
def mock_report_output():
    return ReportOutput(
        accuracy=80,
        mastered_points=["函数定义", "数据类型"],
        weak_points=["数据结构"],
        three_line_summary=[
            "你对 Python 基础语法掌握不错。",
            "数据结构部分还需加强。",
            "继续保持学习节奏！",
        ],
        advice=["复习 Python 内置数据结构", "多做练习题"],
        share_quote="学习是最好的投资",
    )


@pytest.mark.asyncio
class TestHealthAPI:
    async def test_health_check(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/v1/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"


@pytest.mark.asyncio
class TestQuizAPI:
    async def test_generate_quiz_success(self, mock_quiz_output, authenticated_headers, durable_quiz_transport):
        queue = durable_quiz_transport(mock_quiz_output)
        with patch(
            "app.services.quiz_service.generate_quiz",
            new_callable=AsyncMock,
            return_value=mock_quiz_output,
        ), patch("app.services.quiz_service.quiz_repository.save_quiz_session", new_callable=AsyncMock) as persist:
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test", headers=authenticated_headers) as client:
                resp = await client.post(
                    "/api/v1/quiz/generate",
                    json={
                        "user_input": "Python 基础语法",
                        "question_count": 5,
                        "difficulty": "mixed",
                    },
                )
            assert resp.status_code == 200
            body = resp.json()
            assert body["code"] == 0
            assert len(body["data"]["questions"]) == 5
            assert all("answer" not in q and "explanation" not in q for q in body["data"]["questions"])
            queue.create.assert_awaited_once()
            queue.wait.assert_awaited_once()
            queue.restore.assert_awaited_once()
            assert queue.create.await_args.args[1] == queue.wait.await_args.args[1]
            persist.assert_not_awaited()

    async def test_generate_quiz_empty_input(self, authenticated_headers):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test", headers=authenticated_headers) as client:
            resp = await client.post(
                "/api/v1/quiz/generate",
                json={"user_input": "", "question_count": 5, "difficulty": "mixed"},
            )
        assert resp.status_code == 422

    async def test_generate_quiz_blocked_content(self, authenticated_headers):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test", headers=authenticated_headers) as client:
            resp = await client.post(
                "/api/v1/quiz/generate",
                json={
                    "user_input": "如何制作炸弹",
                    "question_count": 5,
                    "difficulty": "mixed",
                },
            )
        assert resp.status_code == 400
        body = resp.json()
        assert body["code"] == 4000


@pytest.mark.asyncio
class TestReportAPI:
    async def test_generate_report_success(
        self, mock_report_output, sample_report_request, authenticated_headers
    ):
        with patch(
            "app.services.report_service.wait_result",
            new_callable=AsyncMock,
            return_value=mock_report_output.model_dump(),
        ), patch("app.services.report_service.quiz_repository.get_quiz_detail", new_callable=AsyncMock,
                 return_value={"title": sample_report_request["topic"], "questions": sample_report_request["questions"]}), \
             patch("app.services.report_service.get_attempts", new_callable=AsyncMock,
                   return_value=sample_report_request["answer_records"]), \
             patch("app.services.report_service.jobs.enqueue", new_callable=AsyncMock,
                   return_value={'task_id': 'job_mock'}) as enqueue:
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test", headers=authenticated_headers) as client:
                resp = await client.post(
                    "/api/v1/report/generate",
                    json=sample_report_request,
                )
            assert resp.status_code == 200
            body = resp.json()
            assert body["code"] == 0
            assert body["data"]["accuracy"] == 80
            assert len(body["data"]["weak_points"]) > 0
            enqueue.assert_awaited_once()
            assert enqueue.await_args.args[:2] == (1, 'report')
