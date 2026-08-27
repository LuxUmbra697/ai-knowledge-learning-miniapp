# AI知识库智能学习小程序

<div align="center">

An AI-powered WeChat mini app for topic-based quiz generation, knowledge-base learning, and intelligent study reports.

<br />

<a href="#简体中文">
  <img src="https://img.shields.io/badge/Language-简体中文-1677ff?style=for-the-badge" alt="简体中文" />
</a>
<a href="#english">
  <img src="https://img.shields.io/badge/Language-English-111827?style=for-the-badge" alt="English" />
</a>

</div>

---

## Table of Contents

- [简体中文](#简体中文)
  - [项目简介](#项目简介)
  - [核心特性](#核心特性)
  - [技术栈](#技术栈)
  - [项目结构](#项目结构)
  - [快速开始](#快速开始)
  - [环境变量](#环境变量)
  - [测试](#测试)
  - [部署](#部署)
- [English](#english)
  - [Overview](#overview)
  - [Features](#features)
  - [Tech Stack](#tech-stack)
  - [Project Structure](#project-structure)
  - [Quick Start](#quick-start)
  - [Environment Variables](#environment-variables)
  - [Testing](#testing)
  - [Deployment](#deployment)

---

## 简体中文

### 项目简介

AI知识库智能学习小程序是一个面向微信生态的智能学习产品。用户可以输入任意学习主题，或上传私有知识文档，系统会结合大模型、联网搜索与知识库检索能力，自动生成题目、提供讲解，并输出学习复盘报告，形成完整的学习闭环。

### 核心特性

- AI 自动出题：基于用户输入主题生成学习题目
- 联网搜索增强：结合 Tavily 获取最新知识上下文
- 知识库出题：支持 PDF、Word、Markdown、TXT 文档上传与 RAG 检索
- 即时讲解反馈：答题后立即返回答案与解析
- AI 学习复盘：生成掌握度、薄弱点与学习建议
- 题目配图能力：支持 AI 生成配图并存储到腾讯云 COS
- 微信用户体系：支持登录、历史记录与报告回看
- 云端部署：支持 Docker 容器化部署到微信云托管

### 技术栈

| 模块 | 技术 |
| --- | --- |
| 小程序前端 | Taro 4、React 18、TypeScript、Sass |
| 后端服务 | Python 3.11、FastAPI、Pydantic v2、Uvicorn |
| AI 编排 | LangChain、LangGraph |
| 模型与检索 | DeepSeek、阿里云百炼、Tavily |
| 向量数据库 | Chroma |
| 数据存储 | MySQL、腾讯云 COS |
| 鉴权 | 微信 `jscode2session`、JWT |
| 测试 | pytest、pytest-asyncio |
| 部署 | Docker、微信云托管 |

### 项目结构

```text
.
├── backend/        # FastAPI 后端服务
├── frontend/       # Taro 微信小程序前端
├── docs/           # 项目文档（本地保留）
├── openspec/       # 规格文档（本地保留）
└── prototypes/     # 原型文件（本地保留）
```

### 快速开始

#### 1. 启动后端

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

#### 2. 启动前端

```bash
cd frontend
npm install
npm run dev:weapp
```

然后使用微信开发者工具打开 `frontend/dist`。

### 环境变量

后端运行依赖 `.env` 配置，请基于 `backend/.env.example` 创建本地环境变量文件。

```bash
cd backend
copy .env.example .env
```

生产环境请通过部署平台环境变量注入真实配置，不要提交敏感信息到仓库。

### 测试

```bash
cd backend
pytest
```

### 部署

项目已提供微信云托管可用的容器配置：

- `backend/Dockerfile`
- `backend/.dockerignore`

后端可以直接通过 Docker 容器方式部署到微信云托管或其他兼容平台。

---

## English

### Overview

AI Knowledge Base Smart Learning Mini App is an intelligent learning product built for the WeChat ecosystem. Users can enter any learning topic or upload private knowledge documents, and the system uses LLMs, web search, and knowledge-base retrieval to generate quizzes, explanations, and learning reports in a complete study workflow.

### Features

- AI-powered quiz generation based on user topics
- Web search enhancement with Tavily for up-to-date context
- Knowledge-base quiz generation with PDF, Word, Markdown, and TXT uploads
- Instant answer checking and explanations
- AI learning report with mastery analysis and suggestions
- AI-generated question illustrations with Tencent COS storage
- WeChat user system with login, history, and report review
- Docker-based deployment for WeChat Cloud Run

### Tech Stack

| Layer | Technology |
| --- | --- |
| Mini App Frontend | Taro 4, React 18, TypeScript, Sass |
| Backend | Python 3.11, FastAPI, Pydantic v2, Uvicorn |
| AI Orchestration | LangChain, LangGraph |
| Models & Retrieval | DeepSeek, Alibaba Bailian, Tavily |
| Vector Store | Chroma |
| Storage | MySQL, Tencent COS |
| Auth | WeChat `jscode2session`, JWT |
| Testing | pytest, pytest-asyncio |
| Deployment | Docker, WeChat Cloud Run |

### Project Structure

```text
.
├── backend/        # FastAPI backend
├── frontend/       # Taro-based WeChat mini app frontend
├── docs/           # project docs (kept locally)
├── openspec/       # spec files (kept locally)
└── prototypes/     # prototype files (kept locally)
```

### Quick Start

#### 1. Start the backend

```bash
cd backend
python -m venv venv
venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Available endpoints after startup:

- `http://localhost:8000/docs`
- `http://localhost:8000/api/v1/health`

#### 2. Start the frontend

```bash
cd frontend
npm install
npm run dev:weapp
```

Then open `frontend/dist` in WeChat DevTools.

### Environment Variables

The backend relies on `.env` configuration. Create a local environment file from `backend/.env.example`.

```bash
cd backend
copy .env.example .env
```

For production, inject real secrets through your deployment platform instead of committing them into the repository.

### Testing

```bash
cd backend
pytest
```

### Deployment

This project already includes container files for WeChat Cloud Run:

- `backend/Dockerfile`
- `backend/.dockerignore`

The backend can be deployed as a Docker container to WeChat Cloud Run or other compatible platforms.
