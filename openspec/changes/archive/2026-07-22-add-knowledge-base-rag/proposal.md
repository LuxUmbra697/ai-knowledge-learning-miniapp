## Why

当前 AI 出题只能依赖大模型自身训练数据或联网搜索获取的公开信息，无法覆盖用户的私有知识（企业内部培训资料、客服知识库、特定题库文档、内部文档等）。需求分析文档中明确提出小程序应支持用户自由输入学习内容，"甚至是一个文档"。本变更补齐这一能力：允许用户上传私有文档（PDF / Word / Markdown），基于向量检索（RAG）从文档内容出题，并与现有联网搜索能力组合成 Agentic RAG（AI 自主判断使用知识库检索还是联网搜索）。

## What Changes

- 新增用户文档上传与知识库管理能力：上传 PDF/Word/Markdown 文档 → 异步解析、分块、向量化（百炼 text-embedding-v4）、存入 Chroma（每用户一个 collection，按 doc_id 元数据隔离）→ 状态轮询（processing/ready/failed）→ 列表/删除。
- 新增基于知识库文档的出题能力：用户在知识库页选择一篇已就绪的文档，一键发起"闯关"，后端使用 Agentic RAG（在原有联网搜索 Agent 基础上新增 `search_knowledge_base` 检索工具）自主决定检索知识库、联网补充或两者结合，作为出题参考资料注入现有出题 Prompt。
- 复用并扩展现有异步任务出题链路（`/quiz/generate/async` + `/quiz/task/{task_id}`），新增可选 `doc_id` 参数，不提供时行为与现状完全一致。
- 新增前端"知识库"页面：文档上传、状态展示、删除、一键闯关入口；在"我的"页新增入口。

## Capabilities

### New Capabilities
- `knowledge-base-documents`: 用户上传、解析、向量化、列表与删除私有文档的能力，包括格式校验、大小/数量限制、异步处理与状态跟踪。
- `knowledge-base-quiz-generation`: 基于用户指定知识库文档，通过 Agentic RAG（知识库检索工具 + 现有联网搜索工具）生成出题参考资料，并复用现有出题链路生成题目。

### Modified Capabilities
<!-- 现有 openspec/specs/ 为空，此前变更未固化为长期 spec，此处无需修改已归档 spec -->

## Impact

- **新增后端代码**：`app/repositories/knowledge_repository.py`、`app/services/document_loader_service.py`、`app/services/vector_store_service.py`、`app/services/knowledge_service.py`、`app/services/rag_service.py`、`app/models/knowledge.py`、`app/prompts/rag_prompt.py`、`app/api/v1/routes/knowledge.py`。
- **修改后端代码**：`app/core/db.py`（新增 `kb_documents` 表）、`app/core/config.py`（新增 Embedding/Chroma/知识库限制配置）、`app/models/quiz.py`（`QuizGenerateRequest` 新增可选 `doc_id` 字段）、`app/services/quiz_service.py`（`doc_id` 存在时走 RAG 分支，否则行为不变）、`app/main.py`（注册新路由）。
- **新增依赖**：`langchain-chroma`、`langchain-community`、`chromadb`、`pypdf`、`docx2txt`、`python-multipart`。
- **新增配置**：`DASHSCOPE_API_KEY`、`DASHSCOPE_EMBEDDING_MODEL`、`CHROMA_PERSIST_DIR`、`KB_MAX_DOCUMENTS_PER_USER`、`KB_MAX_FILE_SIZE_MB`。
- **API 接口**：新增 `POST /api/v1/knowledge/documents`（上传）、`GET /api/v1/knowledge/documents`（列表）、`GET /api/v1/knowledge/documents/{doc_id}`（状态查询）、`DELETE /api/v1/knowledge/documents/{doc_id}`（删除）；`POST /api/v1/quiz/generate/async` 请求体新增可选 `doc_id` 字段，不传时现有请求/响应结构和行为完全不变。
- **前端**：新增 `pages/knowledge/index`（上传/列表/删除/一键闯关），`app.config.ts` 注册页面，`services/api.ts` 新增知识库相关接口封装，`pages/profile` 新增入口。
- **不影响**：现有出题（无 `doc_id`）、报告生成、用户系统、答题记录等核心流程零改动。
