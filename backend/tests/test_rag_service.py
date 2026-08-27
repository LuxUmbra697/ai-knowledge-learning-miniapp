"""rag_service 单元测试"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.documents import Document

from app.services import rag_service


@pytest.fixture
def mock_settings_web_enabled():
    settings = MagicMock()
    settings.enable_web_search = True
    settings.tavily_api_key = "tvly-test-key"
    settings.deepseek_model = "deepseek-chat"
    settings.deepseek_base_url = "https://api.deepseek.com"
    settings.deepseek_api_key = "sk-test"
    return settings


@pytest.fixture
def mock_settings_web_disabled():
    settings = MagicMock()
    settings.enable_web_search = False
    settings.tavily_api_key = "tvly-test-key"
    settings.deepseek_model = "deepseek-chat"
    settings.deepseek_base_url = "https://api.deepseek.com"
    settings.deepseek_api_key = "sk-test"
    return settings


class TestKnowledgeBaseTool:
    def test_returns_joined_content_on_success(self):
        docs = [
            Document(page_content="片段一"),
            Document(page_content="片段二"),
        ]
        with patch(
            "app.services.rag_service.vector_store_service.similarity_search",
            return_value=docs,
        ):
            tool = rag_service._build_knowledge_base_tool(user_id=1, doc_id="doc_1")
            result = tool.invoke({"query": "test"})

        assert "片段一" in result
        assert "片段二" in result

    def test_returns_fallback_when_empty(self):
        with patch(
            "app.services.rag_service.vector_store_service.similarity_search",
            return_value=[],
        ):
            tool = rag_service._build_knowledge_base_tool(user_id=1, doc_id="doc_1")
            result = tool.invoke({"query": "test"})

        assert "未检索到相关内容" in result

    def test_returns_fallback_on_exception(self):
        with patch(
            "app.services.rag_service.vector_store_service.similarity_search",
            side_effect=RuntimeError("chroma error"),
        ):
            tool = rag_service._build_knowledge_base_tool(user_id=1, doc_id="doc_1")
            result = tool.invoke({"query": "test"})

        assert "检索失败" in result


@pytest.mark.asyncio
async def test_fetch_rag_context_returns_content_on_success(mock_settings_web_enabled):
    mock_agent = AsyncMock()
    mock_message = MagicMock()
    mock_message.content = "知识库摘要内容"
    mock_agent.ainvoke.return_value = {"messages": [mock_message]}

    with patch(
        "app.services.rag_service.get_settings", return_value=mock_settings_web_enabled
    ), patch("app.services.rag_service._build_agent", return_value=mock_agent):
        result = await rag_service.fetch_rag_context("学一下 RAG", user_id=1, doc_id="doc_1")

    assert result == "知识库摘要内容"
    mock_agent.ainvoke.assert_called_once()


@pytest.mark.asyncio
async def test_fetch_rag_context_truncates_long_content(mock_settings_web_enabled):
    mock_agent = AsyncMock()
    mock_message = MagicMock()
    mock_message.content = "x" * 8000
    mock_agent.ainvoke.return_value = {"messages": [mock_message]}

    with patch(
        "app.services.rag_service.get_settings", return_value=mock_settings_web_enabled
    ), patch("app.services.rag_service._build_agent", return_value=mock_agent):
        result = await rag_service.fetch_rag_context("test", user_id=1, doc_id="doc_1")

    assert len(result) == rag_service.MAX_CONTEXT_LENGTH


@pytest.mark.asyncio
async def test_fetch_rag_context_returns_empty_on_timeout(mock_settings_web_enabled):
    mock_agent = AsyncMock()
    mock_agent.ainvoke.side_effect = asyncio.TimeoutError()

    with patch(
        "app.services.rag_service.get_settings", return_value=mock_settings_web_enabled
    ), patch("app.services.rag_service._build_agent", return_value=mock_agent):
        result = await rag_service.fetch_rag_context("test", user_id=1, doc_id="doc_1")

    assert result == ""


@pytest.mark.asyncio
async def test_fetch_rag_context_returns_empty_on_exception(mock_settings_web_enabled):
    mock_agent = AsyncMock()
    mock_agent.ainvoke.side_effect = RuntimeError("agent error")

    with patch(
        "app.services.rag_service.get_settings", return_value=mock_settings_web_enabled
    ), patch("app.services.rag_service._build_agent", return_value=mock_agent):
        result = await rag_service.fetch_rag_context("test", user_id=1, doc_id="doc_1")

    assert result == ""


@pytest.mark.asyncio
async def test_fetch_rag_context_returns_empty_when_agent_response_empty(
    mock_settings_web_enabled,
):
    mock_agent = AsyncMock()
    mock_agent.ainvoke.return_value = {"messages": []}

    with patch(
        "app.services.rag_service.get_settings", return_value=mock_settings_web_enabled
    ), patch("app.services.rag_service._build_agent", return_value=mock_agent):
        result = await rag_service.fetch_rag_context("test", user_id=1, doc_id="doc_1")

    assert result == ""


def test_build_agent_excludes_web_tools_when_disabled(mock_settings_web_disabled):
    with patch(
        "app.services.rag_service.get_settings", return_value=mock_settings_web_disabled
    ), patch("langgraph.prebuilt.create_react_agent") as mock_create_agent, patch(
        "langchain_openai.ChatOpenAI"
    ):
        rag_service._build_agent(user_id=1, doc_id="doc_1")

        _, kwargs = mock_create_agent.call_args
        tool_names = [t.name for t in kwargs["tools"]]
        assert tool_names == ["search_knowledge_base"]


def test_build_agent_includes_web_tools_when_enabled(mock_settings_web_enabled):
    with patch(
        "app.services.rag_service.get_settings", return_value=mock_settings_web_enabled
    ), patch("langgraph.prebuilt.create_react_agent") as mock_create_agent, patch(
        "langchain_openai.ChatOpenAI"
    ):
        rag_service._build_agent(user_id=1, doc_id="doc_1")

        _, kwargs = mock_create_agent.call_args
        tool_names = [t.name for t in kwargs["tools"]]
        assert "search_knowledge_base" in tool_names
        assert "tavily_search_basic" in tool_names
        assert "tavily_search_deep" in tool_names
        assert "tavily_extract" in tool_names
