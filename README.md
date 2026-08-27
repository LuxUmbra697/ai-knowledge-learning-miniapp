# LuxUmbra AI 闯关学习小程序

一个面向微信生态的 AI 学习产品，支持基于任意主题自动生成闯关题目、即时讲解、复盘报告、知识库出题与学习记录沉淀。

## 项目概览

LuxUmbra AI 闯关学习小程序的核心目标，是把“输入一个想学的主题”转化为一套可直接完成的学习闭环：

- 输入学习主题
- AI 联网检索与生成题目
- 用户逐题闯关答题
- 系统即时判分与讲解
- 生成 AI 复盘报告
- 沉淀学习记录与知识库资产

项目采用前后端分离架构：

- 前端：Taro 4 + React 18 + TypeScript
- 后端：FastAPI + LangChain + LangGraph
- AI 能力：DeepSeek、阿里云百炼、Tavily
- 部署：Docker + 微信云托管

## 核心能力

- AI 出题：根据用户输入主题自动生成单选、多选、判断题
- 联网增强：结合 Tavily 搜索最新资料，降低题目过时风险
- 即时讲解：答题后立即返回正确答案与解析
- 学习复盘：生成掌握度、薄弱点、总结与建议
- 知识库出题：支持上传 PDF、Word、Markdown、TXT 文档后基于 RAG 出题
- 配图能力：支持按知识点生成题目插图并持久化到 COS
- 用户体系：支持微信登录、闯关历史、报告回看
- 云端部署：可直接通过 Docker 部署到微信云托管

## 技术栈

| 层面    | 技术                                      |
| ----- | --------------------------------------- |
| 小程序前端 | Taro 4、React 18、TypeScript、Sass         |
| 后端服务  | Python 3.11、FastAPI、Pydantic v2、Uvicorn |
| AI 编排 | LangChain、LangGraph、langchain-openai    |
| 模型与检索 | DeepSeek、阿里云百炼、Tavily                   |
| 向量检索  | Chroma                                  |
| 数据存储  | MySQL、腾讯云 COS                           |
| 鉴权    | 微信 `jscode2session`、JWT                 |
| 测试    | pytest、pytest-asyncio                   |
| 部署    | Docker、微信云托管                            |

## 目录结构

```text
luxumbra-ai-learn/
├── backend/        # FastAPI 后端服务
├── frontend/       # Taro 微信小程序前端
├── docs/           # 项目文档
├── openspec/       # 规格与变更文档
└── prototypes/     # 交互原型与设计稿
```

## 适用场景

- AI 学习类产品原型
- 小程序 + AI 应用整合项目
- RAG 知识库学习工具
- 企业培训 / 题库练习 / 考试复习类系统
- 个人作品集中的 AI Agent / LLM 应用项目

## 本地运行

### 环境要求

- Python >= 3.11
- Node.js >= 18
- MySQL >= 8.0
- 微信开发者工具

### 启动后端

```bash
cd backend
python -m venv venv
venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

后端启动后可访问：

- `http://localhost:8000/docs`
- `http://localhost:8000/api/v1/health`

### 启动前端

```bash
cd frontend
npm install
npm run dev:weapp
```

然后使用微信开发者工具打开 `frontend/dist`。

## 环境变量

后端依赖 `.env` 配置运行。建议基于 [backend/.env.example](file:///e:/project/projectAI/lux-ai-learn-fuben/backend/.env.example) 创建本地环境变量文件：

```bash
cd backend
copy .env.example .env
```

生产环境请通过平台环境变量功能注入密钥，不要将真实配置提交到仓库。

## 测试

```bash
cd backend
pytest
```

## 部署

项目已提供适配微信云托管的容器化配置：

- [backend/Dockerfile](file:///e:/project/projectAI/lux-ai-learn-fuben/backend/Dockerfile)
- [backend/.dockerignore](file:///e:/project/projectAI/lux-ai-learn-fuben/backend/.dockerignore)

可将后端服务以 Docker 容器方式部署到微信云托管或其他兼容平台。

<br />

