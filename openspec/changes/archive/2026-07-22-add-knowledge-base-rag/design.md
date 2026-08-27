## Context

项目现有出题链路：`app/api/v1/routes/quiz.py` → `app/services/quiz_service.py` → （可选）`app/services/search_service.py`（联网搜索 Agent，基于 `langgraph.prebuilt.create_react_agent` + `langchain-tavily`）→ `app/llm/quiz_chain.py`（`ChatPromptTemplate | ChatOpenAI` 生成结构化 JSON）。出题为异步任务模式：`POST /quiz/generate/async` 立即返回 `task_id`，后台 `asyncio.create_task` 执行，写入 `quiz_tasks` 表，前端轮询 `GET /quiz/task/{task_id}`。

数据层使用 `aiomysql` 连接池 + 手写 SQL（无 ORM），表结构在 `app/core/db.py` 的 `SCHEMA_STATEMENTS` 中以 `CREATE TABLE IF NOT EXISTS` 声明，应用启动时自动建表。鉴权使用 JWT（`app/core/auth.py`），`get_current_user`（必选）/ `get_optional_user`（可选）两种依赖。

本变更引入向量数据库 RAG 能力，用户上传私有文档后可作为出题的第三种知识来源（现有两种：模型自身知识、联网搜索）。

## Goals / Non-Goals

**Goals:**
- 支持 PDF / Word(.docx) / Markdown(.md) / 纯文本(.txt) 文档上传，异步解析为向量并持久化存储
- 每个用户的文档相互隔离（按 collection 或 metadata 区分），互不可见
- 出题时可指定某一篇已就绪文档，Agent 自主决定检索知识库、联网搜索或两者结合
- 不引入 doc_id 时，出题行为、接口协议与现状完全一致（零回归）
- 文档解析失败、向量化失败均可降级为明确的失败状态，不导致后端崩溃或任务卡死
- 全部新增后端逻辑具备单元测试覆盖（重外部依赖如 Embedding API、Chroma 网络调用均通过 mock/fake 隔离）

**Non-Goals:**
- 不支持视频/网页 URL 转知识库文档（本期仅文件上传，网页场景已有联网搜索覆盖）
- 不做文档内容在线预览/高亮定位
- 不做跨用户共享知识库、团队协作
- 不做增量更新单篇文档（重新上传 = 新建一篇，旧文档需手动删除）
- 不引入独立的向量数据库服务进程，使用 Chroma 本地持久化模式，与后端进程同生命周期

## Decisions

### 1. 向量数据库：`langchain-chroma` 本地持久化，每用户一个 collection

**选择**：`Chroma(collection_name=f"kb_user_{user_id}", embedding_function=embeddings, persist_directory=settings.chroma_persist_dir)`，同一用户的多篇文档写入同一 collection，通过 metadata `{"doc_id": ..., "source": filename}` 区分文档；检索/删除时用 `where={"doc_id": doc_id}` 过滤。

**理由**：
- collection 隔离用户数据，避免跨用户检索泄露
- 单用户单 collection 而非单文档单 collection，避免用户文档数增多时 collection 数量膨胀，且 Agent 检索时可选择性地按 doc_id 过滤或（未来）跨文档检索
- `persist_directory` 自动持久化到磁盘，重启不丢数据，无需额外部署 Chroma Server

**备选方案**：
- 单文档单 collection：隔离更彻底，但 collection 数量随文档数线性增长，元数据过滤已能满足隔离需求，故不采用
- 使用 Chroma HTTP Server 模式：增加部署复杂度，MVP 阶段不需要

### 2. Embedding：百炼 `text-embedding-v4`，通过 OpenAI 兼容模式接入

**选择**：复用项目已用的 `langchain_openai` 包，用 `OpenAIEmbeddings(model="text-embedding-v4", base_url="https://dashscope.aliyuncs.com/compatible-mode/v1", api_key=settings.dashscope_api_key)`。

**理由**：
- 项目已用 `ChatOpenAI` 以相同方式接入 DeepSeek（`base_url` + `api_key` 切换），模式一致，无需引入 `dashscope` SDK 或 `langchain-community` 的专用 Embedding 类，减少依赖面
- 百炼官方文档明确提供 OpenAI 兼容模式的 Embedding 接口，`text-embedding-v4` 支持该模式

**备选方案**：`langchain_community.embeddings.DashScopeEmbeddings`（需要额外 `dashscope` 包依赖，且需要在 `langchain-community` 中维护，收益不明显，故不采用）

### 3. 文档解析：按扩展名分发到轻量 Loader，Markdown/txt 用 `TextLoader` 而非 `UnstructuredMarkdownLoader`

**选择**：
- `.pdf` → `langchain_community.document_loaders.PyPDFLoader`
- `.docx` → `langchain_community.document_loaders.Docx2txtLoader`
- `.md` / `.txt` → `langchain_community.document_loaders.TextLoader`（`encoding="utf-8"`）

统一后接 `RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=150)` 分块。

**理由**：`UnstructuredMarkdownLoader` 依赖重量级 `unstructured` 库（本身依赖 `libmagic` 等系统库，Windows 环境安装易出问题），而 Markdown/纯文本本质是文本文件，直接按字符分块即可满足出题场景对内容的需求，无需保留标题层级等结构化信息。已与用户确认采用此方案。

### 4. 出题时的知识来源整合：扩展现有搜索 Agent 为 Agentic RAG，而非另建独立链路

**选择**：新增 `app/services/rag_service.py`，其 `fetch_rag_context(user_input, user_id, doc_id)` 函数复用 `search_service.py` 中工具构建的思路：构建同一个 `create_react_agent`，工具列表为：
- `search_knowledge_base`（新增，`@tool` 装饰器包装，闭包捕获 `user_id`/`doc_id`，内部调用 `vector_store_service.similarity_search`）
- `tavily_search_basic` / `tavily_search_deep` / `tavily_extract`（当 `enable_web_search` 且配置了 `tavily_api_key` 时才加入，逻辑与现有 `search_service._build_agent` 一致）

Agent 的 system prompt（`app/prompts/rag_prompt.py`）指导其：优先使用 `search_knowledge_base` 检索用户上传的私有文档；若知识库检索结果不足以覆盖出题需求，可再调用联网搜索工具补充；最终仍输出结构化知识摘要文本（与现有 `fetch_knowledge_context` 返回值类型一致），复用现有出题 Prompt 拼装逻辑，不改动 `quiz_chain.py` 的 Prompt 结构。

`quiz_service.py` 中判断：`req.doc_id` 存在 → 校验文档归属与状态后调用 `rag_service.fetch_rag_context`；否则调用原 `search_service.fetch_knowledge_context`（完全不变）。

**理由**：
- 复用现有"两阶段串行"架构（先取知识摘要，再出题），出题 Prompt/Chain 不受影响，风险最低
- 两个数据源通过同一个 Agent 的工具列表暴露，天然符合"Agentic RAG，Agent 自主选择检索方式"的设计诉求，不需要额外的路由/决策逻辑
- 不修改 `search_service.py` 现有函数签名和行为，avoiding 影响现有单元测试和无 `doc_id` 场景

**备选方案**：直接修改 `search_service.fetch_knowledge_context` 增加 `user_id`/`doc_id` 参数——会侵入现有已测试稳定的函数和测试用例，且语义上"联网搜索"和"知识库+联网"是两种不同场景，拆分为独立模块职责更清晰

### 5. 上传与解析流程：异步任务模式，复用 `quiz_tasks` 的设计范式

**选择**：新增 `kb_documents` 表（`doc_id`、`user_id`、`file_name`、`file_type`、`file_size`、`status`、`chunk_count`、`error_message`）。上传接口 `POST /knowledge/documents`（`UploadFile`）：
1. 校验：登录态（`get_current_user`）、文件扩展名白名单、大小 ≤ `KB_MAX_FILE_SIZE_MB`、用户现有文档数 < `KB_MAX_DOCUMENTS_PER_USER`
2. 保存临时文件到本地磁盘（`./data/uploads/{doc_id}.{ext}`），插入 `kb_documents` 行（`status=processing`），立即返回 `doc_id`
3. `asyncio.create_task` 后台执行：加载解析 → 分块 → 逐批 embedding → 写入 Chroma → 更新 `status=ready`、`chunk_count`；任一步异常则 `status=failed` + `error_message`
4. 前端轮询 `GET /knowledge/documents/{doc_id}` 直至 `ready`/`failed`（与出题任务轮询模式一致，复用相同的前端轮询函数模式）

**理由**：与现有 `quiz_service.create_quiz_task` / `_run_quiz_task` / `task_repository` 的异步任务模式完全一致，团队已熟悉该范式，前端也可复用轮询代码风格，学习成本低

### 6. 删除文档：级联清理 DB 行 + 向量 + 临时文件

**选择**：`DELETE /knowledge/documents/{doc_id}`：校验归属 → `vector_store_service.delete_document(user_id, doc_id)`（`Chroma.delete(where={"doc_id": doc_id})`）→ 删除本地文件 → 删除 `kb_documents` 行。任一子步骤失败仅记录日志，不阻断其余清理动作（尽力清理，避免留下孤儿数据比留下部分脏数据更重要，但都不应导致接口 500）。

## Risks / Trade-offs

- **[新增依赖体积较大（chromadb）]** → 已确认非 Windows 平台特殊依赖问题（纯 Python + sqlite，无需 libmagic 等系统库），可通过 `pip install` 直接安装
- **[Embedding API 调用失败/超时]** → 文档处理任务捕获异常，标记 `status=failed` 并记录 `error_message`，用户可重新上传；不影响出题等其他核心功能
- **[Agentic RAG 引入后出题耗时增加]** → 复用现有 Agent 超时兜底策略（`AGENT_TIMEOUT_SECONDS`），且异步任务模式下前端本就允许长轮询，用户体验不受阻塞影响
- **[用户上传恶意/超大文件]** → 后端强制文件扩展名白名单 + 大小上限 + 单用户文档数上限，拒绝时返回明确错误码，不写入任何数据
- **[本地磁盘存储卸载/迁移风险]** → `persist_directory` 与临时文件目录路径可配置，便于后续迁移到共享存储或对象存储（本期非目标）
- **[doc_id 场景与现有出题共用同一 API 路径/任务表]** → `quiz_tasks`、`QuizGenerateRequest`、任务状态查询完全复用，新增字段均为可选，向后兼容；已在 `quiz_service.py` 中通过分支隔离新老逻辑，降低回归风险

## Migration Plan

1. 部署新版本前，确保 `.env` 中配置 `DASHSCOPE_API_KEY`（Embedding 所需），未配置时知识库上传/出题分支会在解析阶段失败并提示，不影响其余功能
2. 应用启动时 `init_mysql()` 自动创建 `kb_documents` 表（沿用现有自动建表机制），无需手工迁移脚本
3. `CHROMA_PERSIST_DIR`（默认 `backend/data/chroma`）、上传临时目录（默认 `backend/data/uploads`）需保证进程有读写权限，首次运行自动创建
4. 回滚：本变更新增的表、路由、配置均为增量新增，不修改任何现有表结构或现有 API 行为，回滚只需回退代码版本，无需数据回滚脚本

## Open Questions

- 无（关键交互方案已与用户确认：文件选择使用 `wx.chooseMessageFile`；知识库与出题的关联方式采用"知识库页选择文档后一键闯关"；Markdown 使用轻量 TextLoader；文档限制为每用户 10 篇、单文件 ≤ 10MB）
