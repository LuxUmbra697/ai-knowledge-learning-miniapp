"""MySQL 连接与初始化。"""

from __future__ import annotations

from typing import Final

import aiomysql
import structlog

from app.core.config import get_settings

logger = structlog.get_logger()

_pool: aiomysql.Pool | None = None

SCHEMA_STATEMENTS: Final[list[str]] = [
    """
    CREATE TABLE IF NOT EXISTS users (
        id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
        openid VARCHAR(64) NOT NULL,
        nickname VARCHAR(100) NOT NULL DEFAULT '学习者',
        avatar_url VARCHAR(500) NOT NULL DEFAULT '',
        total_xp INT NOT NULL DEFAULT 0,
        created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        PRIMARY KEY (id),
        UNIQUE KEY uk_users_openid (openid)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS quiz_sessions (
        id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
        quiz_id VARCHAR(64) NOT NULL,
        user_id BIGINT UNSIGNED NULL,
        title VARCHAR(255) NOT NULL,
        summary TEXT NULL,
        user_input TEXT NULL,
        questions_json JSON NOT NULL,
        created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (id),
        UNIQUE KEY uk_quiz_sessions_quiz_id (quiz_id),
        KEY idx_quiz_sessions_user_id (user_id),
        KEY idx_quiz_sessions_created_at (created_at),
        CONSTRAINT fk_quiz_sessions_user_id
            FOREIGN KEY (user_id) REFERENCES users (id)
            ON DELETE SET NULL
            ON UPDATE CASCADE
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS answer_records (
        id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
        quiz_id VARCHAR(64) NOT NULL,
        user_id BIGINT UNSIGNED NULL,
        records_json JSON NOT NULL,
        total_questions INT NOT NULL,
        correct_count INT NOT NULL,
        accuracy DECIMAL(5, 2) NOT NULL,
        created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (id),
        UNIQUE KEY uk_answer_records_quiz_id (quiz_id),
        KEY idx_answer_records_user_id (user_id),
        KEY idx_answer_records_created_at (created_at),
        CONSTRAINT fk_answer_records_user_id
            FOREIGN KEY (user_id) REFERENCES users (id)
            ON DELETE SET NULL
            ON UPDATE CASCADE,
        CONSTRAINT fk_answer_records_quiz_id
            FOREIGN KEY (quiz_id) REFERENCES quiz_sessions (quiz_id)
            ON DELETE CASCADE
            ON UPDATE CASCADE
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS reports (
        id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
        quiz_id VARCHAR(64) NOT NULL,
        user_id BIGINT UNSIGNED NULL,
        report_json JSON NOT NULL,
        created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (id),
        UNIQUE KEY uk_reports_quiz_id (quiz_id),
        KEY idx_reports_user_id (user_id),
        KEY idx_reports_created_at (created_at),
        CONSTRAINT fk_reports_user_id
            FOREIGN KEY (user_id) REFERENCES users (id)
            ON DELETE SET NULL
            ON UPDATE CASCADE,
        CONSTRAINT fk_reports_quiz_id
            FOREIGN KEY (quiz_id) REFERENCES quiz_sessions (quiz_id)
            ON DELETE CASCADE
            ON UPDATE CASCADE
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS quiz_tasks (
        id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
        task_id VARCHAR(64) NOT NULL,
        user_id BIGINT UNSIGNED NULL,
        status ENUM('pending', 'running', 'completed', 'failed') NOT NULL DEFAULT 'pending',
        user_input TEXT NOT NULL,
        question_count INT NOT NULL DEFAULT 5,
        difficulty VARCHAR(10) NOT NULL DEFAULT 'mixed',
        result_json JSON NULL,
        error_message VARCHAR(500) NULL,
        created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        PRIMARY KEY (id),
        UNIQUE KEY uk_quiz_tasks_task_id (task_id),
        KEY idx_quiz_tasks_user_id (user_id),
        KEY idx_quiz_tasks_status (status)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS kb_documents (
        id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
        doc_id VARCHAR(64) NOT NULL,
        user_id BIGINT UNSIGNED NOT NULL,
        file_name VARCHAR(255) NOT NULL,
        file_type VARCHAR(20) NOT NULL,
        file_size INT NOT NULL,
        status ENUM('processing', 'ready', 'failed') NOT NULL DEFAULT 'processing',
        chunk_count INT NOT NULL DEFAULT 0,
        error_message VARCHAR(500) NULL,
        created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        PRIMARY KEY (id),
        UNIQUE KEY uk_kb_documents_doc_id (doc_id),
        KEY idx_kb_documents_user_id (user_id),
        CONSTRAINT fk_kb_documents_user_id
            FOREIGN KEY (user_id) REFERENCES users (id)
            ON DELETE CASCADE
            ON UPDATE CASCADE
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS image_generation_logs (
        id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
        user_id BIGINT UNSIGNED NOT NULL,
        quiz_id VARCHAR(64) NULL,
        question_id VARCHAR(32) NULL,
        image_url VARCHAR(500) NOT NULL,
        created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (id),
        KEY idx_image_gen_logs_user_created (user_id, created_at)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
]


async def init_mysql() -> None:
    """初始化数据库与基础表结构。"""
    global _pool

    if _pool is not None:
        return

    settings = get_settings()

    bootstrap_conn = await aiomysql.connect(
        host=settings.mysql_host,
        port=settings.mysql_port,
        user=settings.mysql_user,
        password=settings.mysql_password,
        charset=settings.mysql_charset,
        autocommit=True,
    )
    try:
        async with bootstrap_conn.cursor() as cursor:
            await cursor.execute(
                f"CREATE DATABASE IF NOT EXISTS `{settings.mysql_database}` "
                f"CHARACTER SET {settings.mysql_charset} COLLATE utf8mb4_unicode_ci"
            )
    finally:
        bootstrap_conn.close()

    _pool = await aiomysql.create_pool(
        host=settings.mysql_host,
        port=settings.mysql_port,
        user=settings.mysql_user,
        password=settings.mysql_password,
        db=settings.mysql_database,
        charset=settings.mysql_charset,
        minsize=settings.mysql_pool_minsize,
        maxsize=settings.mysql_pool_maxsize,
        autocommit=True,
    )

    async with _pool.acquire() as conn:
        async with conn.cursor() as cursor:
            for statement in SCHEMA_STATEMENTS:
                await cursor.execute(statement)

    logger.info("mysql_initialized", database=settings.mysql_database)


def get_mysql_pool() -> aiomysql.Pool | None:
    return _pool


async def close_mysql_pool() -> None:
    global _pool

    if _pool is None:
        return

    _pool.close()
    await _pool.wait_closed()
    _pool = None
    logger.info("mysql_pool_closed")
