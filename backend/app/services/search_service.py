"""知识获取服务 - 使用 AI Agent 联网搜索获取最新知识"""

import asyncio
import time

import structlog

from app.core.config import get_settings
from app.prompts.search_prompt import SEARCH_AGENT_SYSTEM_PROMPT

logger = structlog.get_logger()

MAX_CONTEXT_LENGTH = 5000
AGENT_TIMEOUT_SECONDS = 120


def _build_agent():
    """构建知识获取 Agent（带 3 个 Tavily 工具）"""
    from langchain_core.callbacks import AsyncCallbackHandler
    from langgraph.prebuilt import create_react_agent
    from langchain_openai import ChatOpenAI
    from langchain_tavily import TavilyExtract, TavilySearch

    settings = get_settings()

    class _ToolLogger(AsyncCallbackHandler):
        """记录每个工具调用的参数和结果"""

        async def on_tool_start(self, serialized, input_str, *, run_id, **kwargs):
            tool_name = serialized.get("name", "unknown")
            logger.info("tool_call_start", tool=tool_name, input=str(input_str)[:500])

        async def on_tool_end(self, output, *, run_id, **kwargs):
            logger.info("tool_call_end", output_length=len(str(output)), output_preview=str(output)[:500])

        async def on_tool_error(self, error, *, run_id, **kwargs):
            logger.warning("tool_call_error", error=str(error)[:300])

        async def on_llm_start(self, serialized, prompts, *, run_id, **kwargs):
            logger.debug("llm_call_start", model=serialized.get("kwargs", {}).get("model", "unknown"))

        async def on_llm_end(self, response, *, run_id, **kwargs):
            # 打印 LLM 返回的 tool_calls 决策
            try:
                gen = response.generations[0][0]
                msg = getattr(gen, "message", None)
                if msg and getattr(msg, "tool_calls", None):
                    logger.info("llm_tool_decision", tool_calls=[
                        {"name": tc["name"], "args": str(tc["args"])[:200]}
                        for tc in msg.tool_calls
                    ])
                else:
                    content = getattr(msg, "content", "") if msg else str(gen)[:200]
                    logger.debug("llm_call_end", content_preview=str(content)[:200])
            except Exception:
                logger.debug("llm_call_end", raw=str(response)[:200])

    tool_logger = _ToolLogger()

    # 轻量搜索：摘要，快速
    tavily_search_basic = TavilySearch(
        name="tavily_search_basic",
        description="轻量搜索，返回最多 10 条结果的摘要。适合首轮广泛搜索，快速了解主题全貌，帮助判断正确领域。",
        max_results=10,
        include_raw_content=False,
        include_answer=False,
        tavily_api_key=settings.tavily_api_key,
    )

    # 深度搜索：完整内容，深入
    tavily_search_deep = TavilySearch(
        name="tavily_search_deep",
        description="深度搜索，返回最多 10 条结果的完整页面内容。适合深入了解专业、小众或容易混淆的主题，获取详细知识。",
        max_results=10,
        include_raw_content=True,
        include_answer=False,
        tavily_api_key=settings.tavily_api_key,
    )

    # URL 内容提取
    tavily_extract = TavilyExtract(
        name="tavily_extract",
        description="从指定 URL 提取页面完整内容。当用户输入包含网址时使用。",
        extract_depth="basic",
        tavily_api_key=settings.tavily_api_key,
    )

    tools = [tavily_search_basic, tavily_search_deep, tavily_extract]

    llm = ChatOpenAI(
        model=settings.deepseek_model,
        base_url=settings.deepseek_base_url,
        api_key=settings.deepseek_api_key,
        temperature=0.1,
        callbacks=[tool_logger],
    )

    agent = create_react_agent(
        llm,
        tools=tools,
        prompt=SEARCH_AGENT_SYSTEM_PROMPT,
    )

    return agent, tool_logger


async def fetch_knowledge_context(user_input: str) -> str:
    """获取知识上下文：使用 AI Agent 联网搜索/提取最新知识。

    Args:
        user_input: 用户输入的学习内容（可能是关键词、一段话或 URL）

    Returns:
        知识摘要字符串，失败时返回空字符串
    """
    settings = get_settings()

    # 配置开关检查
    if not settings.enable_web_search:
        logger.info("web_search_disabled")
        return ""

    if not settings.tavily_api_key:
        logger.warning("tavily_api_key_not_configured")
        return ""

    try:
        logger.info("search_agent_starting", user_input=user_input[:100])

        t0 = time.monotonic()
        agent, tool_logger = _build_agent()
        logger.debug("search_agent_built", elapsed_ms=round((time.monotonic() - t0) * 1000))

        # 使用 asyncio.wait_for 设置超时
        t1 = time.monotonic()
        result = await asyncio.wait_for(
            agent.ainvoke(
                {"messages": [{"role": "user", "content": user_input}]},
                config={"recursion_limit": 10, "callbacks": [tool_logger]},
            ),
            timeout=AGENT_TIMEOUT_SECONDS,
        )
        elapsed = round((time.monotonic() - t1) * 1000)

        # 打印 Agent 完整消息链路用于调试
        messages = result.get("messages", [])
        logger.info(
            "search_agent_completed",
            elapsed_ms=elapsed,
            message_count=len(messages),
            message_types=[type(m).__name__ for m in messages],
        )
        for i, msg in enumerate(messages):
            msg_type = type(msg).__name__
            content_preview = str(getattr(msg, "content", ""))[:200]
            tool_calls = getattr(msg, "tool_calls", None)
            logger.debug(
                "search_agent_message",
                index=i,
                type=msg_type,
                content_preview=content_preview,
                tool_calls=len(tool_calls) if tool_calls else 0,
            )

        # 提取 Agent 最终回复
        content = result["messages"][-1].content
        if not content:
            logger.warning("search_agent_empty_response")
            return ""

        # 截断到最大长度
        if len(content) > MAX_CONTEXT_LENGTH:
            content = content[:MAX_CONTEXT_LENGTH]
            logger.info("search_context_truncated", original_length=len(result["messages"][-1].content))

        logger.info("search_context_fetched", length=len(content))
        return content

    except asyncio.TimeoutError:
        elapsed = round((time.monotonic() - t1) * 1000) if 't1' in dir() else -1
        logger.warning("search_agent_timeout", timeout=AGENT_TIMEOUT_SECONDS, elapsed_ms=elapsed, user_input=user_input[:100])
        return ""
    except Exception as e:
        logger.warning("search_agent_error", error=str(e), error_type=type(e).__name__, user_input=user_input[:100])
        return ""
