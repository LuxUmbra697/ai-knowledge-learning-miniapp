## 1. 依赖与配置

- [x] 1.1 在 `requirements.txt` 中新增 `langchain-chroma`、`langchain-community`、`chromadb`、`pypdf`、`docx2txt`、`python-multipart`
- [x] 1.2 在 `app/core/config.py` 的 `Settings` 中新增：`dashscope_api_key`、`dashscope_embedding_model`（默认 `text-embedding-v4`）、`dashscope_base_url`（默认 `https://dashscope.aliyuncs.com/compatible-mode/v1`）、`chroma_persist_dir`（默认 `./data/chroma`）、`kb_upload_dir`（默认 `./data/uploads`）、`kb_max_documents_per_user`（默认 10）、`kb_max_file_size_mb`（默认 10）、`kb_chunk_size`（默认 1000）、`kb_chunk_overlap`（默认 150）、`kb_retrieve_top_k`（默认 4）
- [x] 1.3 在 `app/core/db.py` 的 `SCHEMA_STATEMENTS` 中追加 `kb_documents` 表（`doc_id`、`user_id`、`file_name`、`file_type`、`file_size`、`status` ENUM('processing','ready','failed')、`chunk_count`、`error_message`、时间戳），不修改任何现有表语句

## 2. 数据访问层

- [x] 2.1 新建 `app/repositories/knowledge_repository.py`：`create_document`、`update_document_status`、`get_document`（含 user_id 校验）、`list_documents(user_id)`、`count_documents(user_id)`、`delete_document(doc_id)`，遵循现有仓储层 `pool is None` 时静默降级的模式
- [x] 2.2 为 `knowledge_repository.py` 编写单元测试（mock `get_mysql_pool`，验证 SQL 调用参数，参照 `task_repository` 的测试风格新增）

## 3. 文档解析

- [x] 3.1 新建 `app/services/document_loader_service.py`：`load_and_split(file_path: str, file_type: str) -> list[Document]`，按扩展名分发 `PyPDFLoader` / `Docx2txtLoader` / `TextLoader`，统一经 `RecursiveCharacterTextSplitter` 分块；不支持的扩展名抛出明确异常
- [x] 3.2 编写测试：构造临时 `.pdf`/`.docx`/`.md`/`.txt` fixture 文件，验证各 Loader 分支正确加载并分块；验证不支持格式抛异常

## 4. 向量存储

- [x] 4.1 新建 `app/services/vector_store_service.py`：`get_embeddings()`（`OpenAIEmbeddings` + DashScope base_url/api_key）、`get_user_vector_store(user_id)`（`Chroma` 实例，`collection_name=f"kb_user_{user_id}"`，`persist_directory=settings.chroma_persist_dir`）、`add_document_chunks(user_id, doc_id, chunks)`（写入前对每个 chunk 补充 `doc_id`/`user_id` metadata）、`delete_document_vectors(user_id, doc_id)`、`similarity_search(user_id, doc_id, query, k)`
- [x] 4.2 编写测试：使用 `langchain_core.embeddings.DeterministicFakeEmbedding` 替换真实 Embedding，在临时目录中对真实 Chroma 实例执行写入/检索/删除，验证按 `user_id`+`doc_id` 隔离生效（不同 doc_id 的内容互不可见）

## 5. 知识库业务服务与路由

- [x] 5.1 新建 `app/models/knowledge.py`：`KnowledgeDocumentItem`、`KnowledgeUploadResponse`、`KnowledgeStatusResponse`、`KnowledgeListResponse` 等 Pydantic 模型
- [x] 5.2 新建 `app/services/knowledge_service.py`：`handle_upload(user_id, filename, content: bytes) -> KnowledgeUploadResponse`（校验扩展名/大小/数量 → 保存临时文件 → 建 DB 记录 → `asyncio.create_task` 后台处理）、`_process_document(doc_id, user_id, file_path, file_type)`（调用 loader + vector_store_service，更新状态）、`list_documents(user_id)`、`get_document_status(user_id, doc_id)`、`delete_document(user_id, doc_id)`（级联清理，任一步失败仅记录日志）
- [x] 5.3 新建 `app/api/v1/routes/knowledge.py`：`POST /knowledge/documents`（`UploadFile`，`get_current_user`）、`GET /knowledge/documents`、`GET /knowledge/documents/{doc_id}`、`DELETE /knowledge/documents/{doc_id}`，全部使用 `get_current_user` 强制鉴权
- [x] 5.4 在 `app/main.py` 注册 `knowledge.router`
- [x] 5.5 编写 `knowledge_service` 单元测试：覆盖格式/大小/数量校验拒绝场景、上传成功后台处理成功/失败场景、删除的级联清理与失败容错
- [x] 5.6 编写 `knowledge` 路由的集成测试（参照 `tests/test_api.py` 风格），覆盖鉴权、跨用户访问拒绝

## 6. Agentic RAG 检索

- [x] 6.1 新建 `app/prompts/rag_prompt.py`：编写 RAG Agent 的 system prompt，指导其优先使用知识库检索工具，必要时补充联网搜索工具，最终输出结构化知识摘要
- [x] 6.2 新建 `app/services/rag_service.py`：`fetch_rag_context(user_input, user_id, doc_id) -> str`，构建 `search_knowledge_base` 工具（闭包捕获 user_id/doc_id，调用 `vector_store_service.similarity_search`）+（若启用）现有 Tavily 工具，复用 `create_react_agent`；异常/超时降级返回空字符串，日志记录 warning
- [x] 6.3 编写 `rag_service` 单元测试：覆盖仅知识库检索、知识库+联网补充、联网禁用时仅知识库、Agent 异常/超时降级四种场景（mock Agent 与工具，参照 `test_search_service.py` 风格）

## 7. 出题链路集成（不影响现有行为）

- [x] 7.1 在 `app/models/quiz.py` 的 `QuizGenerateRequest` 新增可选字段 `doc_id: str | None = None`
- [x] 7.2 修改 `app/services/quiz_service.py`：新增文档归属/状态校验逻辑（`doc_id` 存在但不属于用户或未 `ready` 时抛出明确异常，任务创建前校验，不进入后台任务）；`_run_quiz_task`（及同步 `handle_quiz_generate`）中，`doc_id` 存在时调用 `rag_service.fetch_rag_context`，否则调用原 `search_service.fetch_knowledge_context`，保持无 `doc_id` 时代码路径与现状完全一致
- [x] 7.3 编写集成测试（参照 `tests/test_quiz_search_integration.py`）：验证无 `doc_id` 时行为与改动前完全一致；验证有效 `doc_id` 时调用 `rag_service.fetch_rag_context` 而非 `search_service.fetch_knowledge_context`；验证非法/未就绪 `doc_id` 被拒绝

## 8. 回归验证

- [x] 8.1 运行全量后端测试套件（`pytest backend/tests`），确认新增测试全部通过且现有测试无回归（121 passed）
- [x] 8.2 手动/脚本验证：不带 `doc_id` 调用 `/quiz/generate/async` 全流程，确认与本变更前行为一致

## 9. 前端 - 知识库页面

- [x] 9.1 在 `frontend/src/services/api.ts` 新增：`uploadKnowledgeDocument`（`Taro.uploadFile`）、`getKnowledgeDocuments`、`getKnowledgeDocumentStatus`、`deleteKnowledgeDocument`，以及对应 TypeScript 类型定义；`generateQuizAsync` 增加可选 `docId` 参数（默认不传，保持向后兼容）
- [x] 9.2 新建 `frontend/src/pages/knowledge/index.tsx` + `index.config.ts` + `index.scss`：文档列表展示（状态标签）、上传入口（`Taro.chooseMessageFile` → `uploadKnowledgeDocument` → 轮询状态）、删除操作、"开始闯关"按钮（仅 `ready` 状态可点击，调用 `generateQuizAsync` 传入 `docId`，复用现有轮询与跳转逻辑）
- [x] 9.3 在 `frontend/src/app.config.ts` 的 `pages` 数组中注册 `pages/knowledge/index`
- [x] 9.4 在 `frontend/src/pages/profile/index.tsx` 新增"我的知识库"入口，跳转到知识库页面

## 10. 联调与文档

- [x] 10.1 本地联调：上传 PDF/Word/Markdown 各一篇，验证状态流转、一键闯关生成题目、删除文档后向量清理生效
- [x] 10.2 更新 `backend/.env` 示例（如项目存在 `.env.example`）补充新增配置项说明；如不存在则在 `README` 或 `docs/` 中简要说明新增环境变量
