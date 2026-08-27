"""知识库 Agentic RAG 检索服务 - 结合知识库向量检索与联网搜索"""

import asyncio
import time

import structlog

from app.core.config import get_settings
from app.prompts.rag_prompt import RAG_AGENT_SYSTEM_PROMPT
from app.services import vector_store_service

logger = structlog.get_logger()

MAX_CONTEXT_LENGTH = 3000
AGENT_TIMEOUT_SECONDS = 60


def _build_knowledge_base_tool(user_id: int, doc_id: str):
    """构建限定 user_id/doc_id 的知识库检索工具"""
    from langchain_core.tools import tool

    @tool
    def search_knowledge_base(query: str) -> str:
        """在用户上传的私有知识库文档中检索与 query 最相关的内容片段，返回拼接后的文本。"""
        try:
            docs = vector_store_service.similarity_search(user_id=user_id, doc_id=doc_id, query=query)
        except Exception as e:
            logger.warning("kb_retrieval_failed", user_id=user_id, doc_id=doc_id, error=str(e))
            return "知识库检索失败，未获取到内容。"

        if not docs:
            return "知识库中未检索到相关内容。"

        return "\n\n".join(doc.page_content for doc in docs)

    return search_knowledge_base


def _build_agent(user_id: int, doc_id: str):
    """构建知识获取 Agent：知识库检索工具 +（可选）联网搜索工具"""
    from langgraph.prebuilt import create_react_agent
    from langchain_openai import ChatOpenAI

    settings = get_settings()

    tools = [_build_knowledge_base_tool(user_id, doc_id)]

    if settings.enable_web_search and settings.tavily_api_key:
        from langchain_tavily import TavilyExtract, TavilySearch

        tools.append(
            TavilySearch(
                name="tavily_search_basic",
                description="轻量联网搜索，返回最多 10 条结果的摘要。用于知识库内容不足时补充背景知识。",
                max_results=10,
                include_raw_content=False,
                include_answer=False,
                tavily_api_key=settings.tavily_api_key,
            )
        )
        tools.append(
            TavilySearch(
                name="tavily_search_deep",
                description="深度联网搜索，返回最多 10 条结果的完整内容。用于知识库内容不足以覆盖专业主题时补充。",
                max_results=10,
                include_raw_content=True,
                include_answer=False,
                tavily_api_key=settings.tavily_api_key,
            )
        )
        tools.append(
            TavilyExtract(
                name="tavily_extract",
                description="从指定 URL 提取页面完整内容。",
                extract_depth="basic",
                tavily_api_key=settings.tavily_api_key,
            )
        )

    llm = ChatOpenAI(
        model=settings.deepseek_model,
        base_url=settings.deepseek_base_url,
        api_key=settings.deepseek_api_key,
        temperature=0.1,
    )

    agent = create_react_agent(
        llm,
        tools=tools,
        prompt=RAG_AGENT_SYSTEM_PROMPT,
    )
    return agent


async def fetch_rag_context(user_input: str, user_id: int, doc_id: str) -> str:
    """基于知识库文档（及可选联网搜索）获取知识摘要，用于出题参考资料。

    Args:
        user_input: 用户输入的学习内容
        user_id: 用户 ID，用于限定检索范围
        doc_id: 知识库文档 ID，用于限定检索范围

    Returns:
        知识摘要字符串，失败时返回空字符串
    """
    try:
        logger.info("rag_agent_starting", user_id=user_id, doc_id=doc_id, user_input=user_input[:100])

        t0 = time.monotonic()
        agent = _build_agent(user_id, doc_id)

        result = await asyncio.wait_for(
            agent.ainvoke(
                {"messages": [{"role": "user", "content": user_input}]},
                config={"recursion_limit": 10},
            ),
            timeout=AGENT_TIMEOUT_SECONDS,
        )
        elapsed = round((time.monotonic() - t0) * 1000)

        messages = result.get("messages", [])
        logger.info(
            "rag_agent_completed",
            elapsed_ms=elapsed,
            message_count=len(messages),
        )

        content = messages[-1].content if messages else ""
        if not content:
            logger.warning("rag_agent_empty_response", user_id=user_id, doc_id=doc_id)
            return ""

        if len(content) > MAX_CONTEXT_LENGTH:
            content = content[:MAX_CONTEXT_LENGTH]

        logger.info("rag_context_fetched", user_id=user_id, doc_id=doc_id, length=len(content))
        return content

    except asyncio.TimeoutError:
        logger.warning(
            "rag_agent_timeout", timeout=AGENT_TIMEOUT_SECONDS, user_id=user_id, doc_id=doc_id
        )
        return ""
    except Exception as e:
        logger.warning(
            "rag_agent_error", error=str(e), error_type=type(e).__name__, user_id=user_id, doc_id=doc_id
        )
        return ""
