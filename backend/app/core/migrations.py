"""Explicit additive migrations; compatible with MySQL 5.7 and 8.0."""

from app.core.db import get_mysql_pool

MIGRATIONS = {
    1: ["""CREATE TABLE IF NOT EXISTS quiz_question_attempts (
        quiz_id VARCHAR(64) NOT NULL,
        user_id BIGINT UNSIGNED NOT NULL,
        question_id VARCHAR(64) NOT NULL,
        record_json JSON NOT NULL,
        created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (quiz_id, user_id, question_id),
        CONSTRAINT fk_attempt_quiz FOREIGN KEY (quiz_id) REFERENCES quiz_sessions(quiz_id) ON DELETE CASCADE,
        CONSTRAINT fk_attempt_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci"""],
    2: [
        "ALTER TABLE users MODIFY openid VARCHAR(64) NULL",
        """CREATE TABLE IF NOT EXISTS account_credentials (
            username VARCHAR(40) NOT NULL PRIMARY KEY,
            user_id BIGINT UNSIGNED NOT NULL UNIQUE,
            password_hash VARCHAR(255) NOT NULL,
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT fk_account_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci""",
        """CREATE TABLE IF NOT EXISTS auth_rate_limits (
            bucket VARCHAR(64) NOT NULL PRIMARY KEY, hits INT NOT NULL,
            expires_at DATETIME NOT NULL, KEY idx_auth_expiry(expires_at)
        ) ENGINE=InnoDB""",
    ],
}


async def migrate():
    pool = get_mysql_pool()
    if pool is None:
        raise RuntimeError("Connect to the migration database first")
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute("SELECT GET_LOCK('ai_learn_schema_migration', 10)")
            if (await cur.fetchone())[0] != 1:
                raise RuntimeError("Migration lock unavailable")
            try:
                await cur.execute("CREATE TABLE IF NOT EXISTS schema_migrations (version INT PRIMARY KEY, applied_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP) ENGINE=InnoDB")
                await cur.execute("SELECT version FROM schema_migrations")
                applied = {row[0] for row in await cur.fetchall()}
                for version, statements in MIGRATIONS.items():
                    if version not in applied:
                        for statement in statements:
                            await cur.execute(statement)
                        await cur.execute("INSERT INTO schema_migrations(version) VALUES (%s)", (version,))
            finally:
                await cur.execute("SELECT RELEASE_LOCK('ai_learn_schema_migration')")
