## 1. 依赖与配置

- [x] 1.1 在 `requirements.txt` 中新增 `langchain-tavily` 和 `langgraph` 依赖
- [x] 1.2 在 `app/core/config.py` 的 `Settings` 类中新增 `tavily_api_key`、`enable_web_search`（默认 True）配置项

## 2. 知识获取 Agent

- [x] 2.1 新建 `app/services/search_service.py`，实现 `fetch_knowledge_context(user_input: str) -> str` 异步函数：实例化 3 个工具（`tavily_search_basic`: max_results=3/include_raw_content=False、`tavily_search_deep`: max_results=5/include_raw_content=True、`tavily_extract`），使用 `create_agent` 构建 ReAct Agent
- [x] 2.2 编写 Agent 的 system prompt（`app/prompts/search_prompt.py`），指导 Agent：分析用户输入判断是关键词还是 URL；根据知识复杂度选择 basic 或 deep 搜索工具；动态调整运行时参数（search_depth、time_range、include_domains 等）；限制最多调用 2 次工具；输出结构化知识摘要
- [x] 2.3 在 `fetch_knowledge_context` 中实现降级逻辑：检查 `enable_web_search` 配置开关；Agent 执行设置 15s 超时；捕获所有异常记录 warning 日志，返回空字符串
- [x] 2.4 实现知识摘要截断：Agent 输出结果超过 3000 字符时截断

## 3. Prompt 改造

- [x] 3.1 修改 `app/prompts/quiz_prompt.py` 的 `QUIZ_HUMAN_PROMPT`，新增 `{search_context}` 占位符区域，当有搜索结果时展示为"参考资料"段落，并指示模型优先基于参考资料出题确保知识准确性
- [x] 3.2 修改 `QUIZ_SYSTEM_PROMPT`，补充提示：当提供了参考资料时，必须优先基于参考资料出题

## 4. 出题链路集成

- [x] 4.1 修改 `app/llm/quiz_chain.py` 的 `generate_quiz` 函数签名，新增 `search_context: str = ""` 参数，传入 Prompt 模板
- [x] 4.2 修改 `app/services/quiz_service.py` 的 `handle_quiz_generate` 函数，在调用 `generate_quiz` 前先调用 `fetch_knowledge_context`，将结果传入 `generate_quiz`

## 5. 测试

- [x] 5.1 为 `search_service.py` 编写单元测试：覆盖轻量搜索、深度搜索、URL 提取、超时降级、配置关闭五种场景
- [x] 5.2 为改造后的出题链路编写集成测试：验证有/无搜索上下文时均能正常生成题目
