## Context

当前项目后端使用 FastAPI + LangChain + DeepSeek，出题流程为：用户输入 → Prompt 拼装 → DeepSeek 生成题目 JSON。模型只依赖训练数据，无法获取截止日期后的新知识。当用户输入较新或小众的主题时，模型可能产出错误内容。

需求分析文档核心流程第 2 步明确要求"AI 自动从全网或者特定的信息源获取知识"，当前是缺失的。

此外，用户输入可能不只是关键词/一段话，还可能是一个网页 URL。系统需要同时支持：
1. 根据关键词搜索并获取最新知识
2. 根据用户提供的网址直接提取页面内容

现有技术栈：
- `langchain-openai` 通过 `ChatOpenAI` 对接 DeepSeek
- `ChatPromptTemplate` 管理 Prompt
- 配置管理使用 `pydantic-settings`
- 已有 `app/services/quiz_service.py` → `app/llm/quiz_chain.py` → `app/prompts/quiz_prompt.py` 的调用链

## Goals / Non-Goals

**Goals:**
- 出题前使用 AI Agent 自主决定如何获取知识：关键词搜索、URL 提取、或两者组合
- Agent 能动态调整工具参数（搜索深度、结果数量、地域范围等），适应不同难度和场景
- 支持用户输入 URL 时直接提取整个网页内容作为出题素材
- 搜索为可选增强，搜索/提取失败时自动降级为纯模型出题
- 对前端 API 完全透明，不改变 `POST /api/v1/quiz/generate` 的请求/响应结构
- 搜索功能可通过配置开关控制

**Non-Goals:**
- 不做 RAG 私有知识库（后续 P1）
- 不做 PDF/Word/视频解析（后续 P1）
- 不做搜索结果缓存或持久化
- 不改报告生成链路

## Decisions

### 1. 搜索服务选型：Tavily Search + Tavily Extract（多实例）

**选择**：使用 LangChain 官方的 `langchain-tavily` 包，实例化 **3 个工具** 供 Agent 选择：

| 工具名 | 类 | 用途 | 实例化参数 |
|--------|-----|------|------------|
| `tavily_search_basic` | `TavilySearch` | 轻量搜索，返回摘要 | `max_results=3`, `include_raw_content=False` |
| `tavily_search_deep` | `TavilySearch` | 深度搜索，返回完整页面内容 | `max_results=5`, `include_raw_content=True` |
| `tavily_extract` | `TavilyExtract` | 从指定 URL 提取页面内容 | `extract_depth="basic"` |

**为什么用多实例而非单实例**：

`TavilySearch` 的 `max_results`、`include_raw_content`、`include_answer` 这三个参数**只能在实例化时设置，不能在调用时动态修改**（LangChain 官方文档明确说明："For reliability and performance reasons, certain parameters that affect response size cannot be modified during invocation"）。

因此用两个不同配置的 `TavilySearch` 实例（basic vs deep），通过不同的 `name` 和 `description` 让 Agent 根据场景自主选择，间接实现了 `include_raw_content` 和 `max_results` 的动态化。

**可被 Agent 运行时动态调整的参数**（通过 Tool Calling 传参）：
- `query` — 搜索关键词
- `search_depth` — "basic" 或 "advanced"
- `time_range` — "day" / "week" / "month" / "year"
- `include_domains` — 限定搜索域名
- `exclude_domains` — 排除搜索域名
- `urls`（TavilyExtract）— 要提取的 URL 列表
- `extract_depth`（TavilyExtract）— "basic" 或 "advanced"

**不需要的参数**：
- `include_answer`：我们要原始素材而非 Tavily 的 AI 总结，固定为 False

**理由**：
- 两类 `TavilySearch` 覆盖轻量/深度两种搜索场景
- `TavilyExtract` 覆盖用户直接输入 URL 的场景
- 三个工具均在 `langchain-tavily` 包中，统一维护，官方持续更新
- 免费额度 1000 次/月，足够 MVP 验证

**备选方案及否决理由**：
- `tavily-python` 裸 SDK：无法让 Agent 自主选择工具和动态传参，需手写大量分支逻辑
- DuckDuckGo Search：无 URL 提取能力，结果质量不稳定，无 `raw_content`
- 自行用 `httpx` + `BeautifulSoup` 抓网页：工程量大、反爬风险高、维护成本高
- 单个 `TavilySearch` 实例动态调所有参数：`max_results` 和 `include_raw_content` 不支持运行时修改，行不通

### 2. 集成方式：LangChain Agent + Tool Calling

**选择**：使用 `langchain.agents.create_agent` 构建 ReAct Agent，将 3 个工具（`tavily_search_basic`、`tavily_search_deep`、`tavily_extract`）绑定给 Agent，让 AI 自主决定调用哪个工具及传什么参数。

**理由**：
- 用户输入形态多样（关键词、一段话、URL、混合内容），硬编码分支逻辑既复杂又脆弱
- Agent 看到 3 个工具的不同 `description`，根据场景自主选择：
  - 简单/常见知识 → 调 `tavily_search_basic`（3 条摘要，快速）
  - 复杂/专业/最新知识 → 调 `tavily_search_deep`（5 条完整内容，深度）
  - 用户输入 URL → 调 `tavily_extract`（提取页面内容）
- Agent 还能在运行时动态调整每次调用的参数：
  - `search_depth="advanced"` vs `"basic"`
  - `time_range="week"` 或 `"month"`（时效性话题）
  - `include_domains=["wikipedia.org", ...]`（限定来源）
- LangChain 官方文档明确推荐此模式：工具参数由 Agent 在运行时动态设置
- 依赖 `langgraph` 作为 Agent 运行时，这是 LangChain 当前推荐的 Agent 执行引擎

**备选方案及否决理由**：
- 固定参数的简单 chain：无法适应用户输入的多样性，每种场景都要手写 if-else
- LangChain 旧版 AgentExecutor：已被官方标记为 legacy，推荐使用 `create_agent` + langgraph

### 3. Agent System Prompt 设计：知识获取专家

**选择**：为知识获取 Agent 设计专门的 system prompt，指导它根据用户输入智能选择工具和参数。

**Agent 职责**：
- 分析用户输入，判断是关键词/文本还是 URL
- 如果包含 URL，使用 `TavilyExtract` 提取页面内容
- 如果是关键词/文本，根据复杂度选择 `tavily_search_basic`（轻量）或 `tavily_search_deep`（深度）
- 动态选择搜索参数：根据时效性选 `time_range`，根据来源需求选 `include_domains`，根据搜索精度选 `search_depth`
- 最终输出结构化的知识摘要，供后续出题 Prompt 使用

**理由**：
- 把"如何获取知识"的决策交给 AI，而非硬编码规则
- Agent 的 system prompt 可以独立迭代优化，不影响出题 Prompt
- 将知识获取和出题生成拆分为两步，职责清晰

### 4. 整体流程：两阶段串行

**选择**：先运行"知识获取 Agent"得到参考资料，再将参考资料注入出题 Prompt 生成题目。

**流程**：
1. 用户输入 → 知识获取 Agent（带 tavily_search_basic + tavily_search_deep + tavily_extract 三个工具）→ 输出知识摘要
2. 知识摘要 + 用户输入 → 出题 Prompt → DeepSeek → 结构化题目 JSON

**理由**：
- 两阶段解耦：知识获取和出题生成各自独立，便于单独测试和优化
- 出题阶段仍使用现有的 `ChatPromptTemplate | llm` chain，保持结构化 JSON 输出的稳定性
- 避免在出题 chain 中引入 Agent/Tool 调用，防止输出格式不可控

### 5. 搜索结果上下文控制

**选择**：Agent 输出的知识摘要限制在 3000 字符以内，注入出题 Prompt 的 human message 中。

**理由**：
- 给 Agent 足够空间获取深度内容（URL 提取的内容可能很长），但在注入出题 Prompt 前截断
- 3000 字符（相比之前的 2000）给 URL 提取场景留出更多余量
- DeepSeek 上下文足够大，3000 字符不会导致性能问题

### 6. 降级策略

**选择**：Agent 执行异常时捕获错误，记录日志，继续用原 Prompt（无搜索上下文）出题。

**理由**：
- 搜索/提取是增强而非必需，不应阻断核心体验
- Agent 超时（15s）也触发降级
- 用户无感知降级，体验连贯

## Risks / Trade-offs

- **[Agent 调用增加出题耗时]** → Agent 设置 15s 总超时，超时则降级；两阶段串行但总耗时可控在 45s 内
- **[Agent 可能过度调用工具]** → system prompt 明确限制：最多调用 2 次工具，获取到足够信息即停止
- **[Tavily 免费额度耗尽]** → 监控用量，额度不足时自动降级为无搜索模式
- **[Agent 输出不稳定]** → Agent 仅负责获取知识摘要（纯文本），不负责生成结构化 JSON，降低不稳定风险
- **[新增依赖 langchain-tavily + langgraph]** → 均为 LangChain 官方维护的核心包，风险可控
- **[URL 提取可能遇到反爬或付费墙]** → `TavilyExtract` 内置处理机制，失败时 Agent 可降级为搜索关键词
