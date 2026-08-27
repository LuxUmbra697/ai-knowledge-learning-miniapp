## Why

当前 AI 出题完全依赖大模型的训练数据，无法覆盖训练截止日期之后的新知识。用户输入一个较新或小众的主题（如 "Harness Engineering"）时，模型可能会基于过时信息或同名歧义概念生成错误的题目和讲解，导致用户学到错误知识。需求分析文档中明确提到 "AI 自动从全网或者特定的信息源获取知识"，这是 MVP 核心流程的第 2 步，现在需要补齐。

## What Changes

- 在后端出题链路中引入 **知识获取 Agent**：基于 LangChain Agent + Tool Calling 模式，让 AI 自主决定如何获取知识。
- 使用 `langchain-tavily` 包接入两个工具：
  - **`TavilySearch`**：关键词搜索，获取最新网络信息，AI 动态调整 `search_depth`、`max_results`、`time_range` 等参数
  - **`TavilyExtract`**：URL 内容提取，用户输入网页时直接获取整个页面内容
- Agent 自主判断用户输入类型（关键词 vs URL vs 混合），选择合适的工具和参数
- 改造出题 Prompt，注入 Agent 获取的知识摘要作为参考资料
- 搜索为**可选增强**：Agent 执行失败时降级为原有纯模型出题，不阻断核心流程
- 在配置中新增搜索相关参数（API Key、开关、默认结果数等）

## Capabilities

### New Capabilities
- `web-search-context`: 出题前通过 AI Agent 智能获取主题相关的最新信息（支持关键词搜索和 URL 内容提取），作为 AI 生成题目的参考上下文。包括知识获取 Agent、TavilySearch/TavilyExtract 工具集成、动态参数选择、降级策略。

### Modified Capabilities
<!-- 无现有 spec 需要修改 -->

## Impact

- **后端代码**：新增 `app/services/search_service.py`、新增 `app/prompts/search_prompt.py`、修改 `app/prompts/quiz_prompt.py`、修改 `app/llm/quiz_chain.py`、修改 `app/services/quiz_service.py`、修改 `app/core/config.py`。
- **依赖**：新增 `langchain-tavily` 和 `langgraph` 到 `requirements.txt`。
- **API 接口**：`POST /api/v1/quiz/generate` 的请求/响应结构不变，内部逻辑增强，对前端透明。
- **配置**：新增 `TAVILY_API_KEY`、`ENABLE_WEB_SEARCH` 环境变量。
