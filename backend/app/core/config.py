"""LuxUmbra-AI闯关学习小程序 - 后端配置"""

from functools import lru_cache
import os
from pathlib import Path

from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    # DeepSeek
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-chat"

    # Tavily (Web Search)
    tavily_api_key: str = ""
    enable_web_search: bool = True

    # DashScope (百炼 Embedding，用于知识库 RAG)
    dashscope_api_key: str = ""
    dashscope_embedding_model: str = "text-embedding-v4"
    dashscope_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    embedding_dimensions: int = Field(default=1024, ge=64, le=4096)
    embedding_timeout_seconds: int = Field(default=15, ge=1, le=60)

    # 知识库 / 向量存储
    chroma_persist_dir: str = "./data/chroma"
    kb_upload_dir: str = "./data/uploads"
    kb_max_documents_per_user: int = 10
    kb_max_file_size_mb: int = 10
    kb_chunk_size: int = 1000
    kb_chunk_overlap: int = 150
    kb_retrieve_top_k: int = 4
    kb_retrieve_candidates: int = Field(default=20, ge=4, le=50)
    kb_reranker: str = 'lexical'
    kb_max_corpus_chunks: int = Field(default=10000, ge=100, le=20000)
    kb_max_pdf_pages: int = Field(default=120, ge=1, le=500)
    kb_max_text_chars: int = Field(default=500000, ge=1000, le=2000000)
    kb_parse_timeout_seconds: int = Field(default=25, ge=1, le=60)
    kb_max_uncompressed_mb: int = Field(default=20, ge=1, le=50)

    # 题目配图（DashScope 千问-文生图 qwen-image）
    dashscope_image_model: str = "qwen-image-2.0"
    # 生图专用 API Key，禁止回退到 Embedding Key。
    # 注意：部分 sk-ws- 开头的工作空间 Key 按用途限定权限范围，Embedding 与生图可能需要各自的 Key。
    dashscope_image_api_key: str = ""
    # 图像生成使用的原生 DashScope API 地址（与 OpenAI 兼容模式的 dashscope_base_url 不同）
    # 留空时会自动从 dashscope_base_url 派生（将 /compatible-mode/v1 替换为 /api/v1）
    dashscope_image_base_url: str = ""
    image_gen_size: str = "512*512"
    image_gen_daily_limit: int = Field(default=20, ge=1, le=100)
    image_gen_max_concurrency: int = 5

    # 腾讯云 COS（用于持久化存储 AI 生成的题目配图）
    cos_secret_id: str = ""
    cos_secret_key: str = ""
    cos_region: str = "ap-shanghai"
    cos_bucket: str = ""
    cos_upload_prefix: str = "quiz-images/"
    # 可选：自定义访问域名（如 CDN 加速域名），留空则使用 COS 默认域名
    cos_domain: str = ""

    # App
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    app_debug: bool = True
    worker_enabled: bool = False
    worker_daily_provider_calls: int = Field(default=100, ge=0, le=1000000)
    worker_daily_provider_input_bytes: int = Field(default=500000, ge=0, le=100000000)

    # JWT
    jwt_secret: str = "change-me-in-production"
    jwt_expire_minutes: int = 43200  # 30 天

    # 微信小程序
    wechat_app_id: str = ""
    wechat_app_secret: str = ""

    # MySQL
    mysql_host: str = "localhost"
    mysql_port: int = 3306
    mysql_user: str = "root"
    mysql_password: str = ""
    mysql_database: str = "luxumbra_ai_learn"
    mysql_charset: str = "utf8mb4"
    mysql_pool_minsize: int = 1
    mysql_pool_maxsize: int = 10
    mysql_auto_init: bool = False

    # Log
    log_level: str = "INFO"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}


@lru_cache
def get_settings() -> Settings:
    filename = os.getenv("AI_LEARN_ENV_FILE", str(Path(__file__).resolve().parents[2] / ".env"))
    return Settings(_env_file=filename or None)
