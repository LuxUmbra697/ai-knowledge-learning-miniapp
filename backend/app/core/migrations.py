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
    3: [
        """CREATE TABLE IF NOT EXISTS kb_index_meta (
            doc_id VARCHAR(64) NOT NULL PRIMARY KEY,
            user_id BIGINT UNSIGNED NOT NULL,
            file_hash CHAR(64) NULL,
            revision INT NOT NULL DEFAULT 1,
            index_version VARCHAR(32) NOT NULL,
            storage_key VARCHAR(100) NOT NULL,
            active BOOLEAN NOT NULL DEFAULT TRUE,
            cleanup_pending BOOLEAN NOT NULL DEFAULT FALSE,
            UNIQUE KEY idx_kb_user_hash(user_id, file_hash),
            KEY idx_kb_owner_active(user_id, active),
            CONSTRAINT fk_kb_meta_doc FOREIGN KEY(doc_id) REFERENCES kb_documents(doc_id) ON DELETE CASCADE,
            CONSTRAINT fk_kb_meta_user FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci""",
        """CREATE TABLE IF NOT EXISTS kb_chunks (
            doc_id VARCHAR(64) NOT NULL,
            chunk_id VARCHAR(64) NOT NULL,
            user_id BIGINT UNSIGNED NOT NULL,
            revision INT NOT NULL,
            index_version VARCHAR(32) NOT NULL,
            content MEDIUMTEXT NOT NULL,
            metadata_json JSON NOT NULL,
            PRIMARY KEY(doc_id, revision, chunk_id),
            KEY idx_kb_chunk_scope(user_id, index_version),
            CONSTRAINT fk_kb_chunk_doc FOREIGN KEY(doc_id) REFERENCES kb_documents(doc_id) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci""",
    ],
    4: [
        """CREATE TABLE IF NOT EXISTS learning_jobs (
            task_id VARCHAR(64) NOT NULL PRIMARY KEY,
            user_id BIGINT UNSIGNED NOT NULL,
            kind VARCHAR(16) NOT NULL,
            idempotency_key VARCHAR(100) NOT NULL,
            fingerprint CHAR(64) NOT NULL,
            active_fingerprint CHAR(64) NULL,
            status ENUM('staging','queued','running','completed','failed','cancelled') NOT NULL DEFAULT 'queued',
            stage VARCHAR(40) NOT NULL DEFAULT 'queued',
            payload_json JSON NOT NULL,
            state_json JSON NOT NULL,
            trace_json JSON NOT NULL,
            result_json JSON NULL,
            error_code VARCHAR(64) NULL,
            error_message VARCHAR(500) NULL,
            lease_token CHAR(32) NULL,
            lease_until DATETIME NULL,
            claims INT NOT NULL DEFAULT 0,
            created_at DATETIME NOT NULL,
            started_at DATETIME NULL,
            updated_at DATETIME NOT NULL,
            config_version VARCHAR(32) NOT NULL DEFAULT 'jobs-v1',
            UNIQUE KEY idx_job_idempotency(user_id,kind,idempotency_key),
            UNIQUE KEY idx_job_active(user_id,kind,active_fingerprint),
            KEY idx_job_claim(status,lease_until,created_at),
            CONSTRAINT fk_job_user FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci""",
    ],
    5: ["ALTER TABLE kb_index_meta ADD COLUMN job_id VARCHAR(64) NULL"],
    6: ["""CREATE TABLE IF NOT EXISTS provider_call_budget (
        budget_day DATE NOT NULL PRIMARY KEY,
        calls INT NOT NULL DEFAULT 0,
        input_bytes BIGINT NOT NULL DEFAULT 0
    ) ENGINE=InnoDB"""],
    7: ["""CREATE TABLE IF NOT EXISTS learning_job_request_keys (
        user_id BIGINT UNSIGNED NOT NULL,
        kind VARCHAR(16) NOT NULL,
        idempotency_key VARCHAR(100) NOT NULL,
        task_id VARCHAR(64) NOT NULL,
        PRIMARY KEY(user_id,kind,idempotency_key),
        KEY idx_request_task(task_id),
        CONSTRAINT fk_request_job FOREIGN KEY(task_id) REFERENCES learning_jobs(task_id) ON DELETE CASCADE
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci"""],
    8: ["""ALTER TABLE learning_job_request_keys DROP FOREIGN KEY fk_request_job,
        ADD CONSTRAINT fk_request_owner FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE"""],
    9: [
        """CREATE TABLE IF NOT EXISTS learning_concepts (
            user_id BIGINT UNSIGNED NOT NULL, concept_id CHAR(64) NOT NULL,
            label VARCHAR(120) NOT NULL, mapping_confidence VARCHAR(40) NOT NULL,
            mastery DOUBLE NOT NULL DEFAULT 0.2, attempts INT NOT NULL DEFAULT 0,
            correct_count INT NOT NULL DEFAULT 0, updated_at DATETIME(6) NOT NULL,
            PRIMARY KEY(user_id,concept_id),
            CONSTRAINT fk_concept_user FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci""",
        """CREATE TABLE IF NOT EXISTS learning_cards (
            card_id VARCHAR(64) NOT NULL PRIMARY KEY, user_id BIGINT UNSIGNED NOT NULL,
            quiz_id VARCHAR(64) NOT NULL, question_id VARCHAR(64) NOT NULL, concept_id CHAR(64) NOT NULL,
            card_json JSON NOT NULL, due_at DATETIME(6) NOT NULL, version INT NOT NULL DEFAULT 1,
            last_correct BOOLEAN NOT NULL, wrong_count INT NOT NULL DEFAULT 0,
            favorite BOOLEAN NOT NULL DEFAULT FALSE, diagnosis VARCHAR(40) NULL,
            created_at DATETIME(6) NOT NULL, updated_at DATETIME(6) NOT NULL,
            UNIQUE KEY idx_card_question(user_id,quiz_id,question_id),
            KEY idx_card_due(user_id,due_at),
            CONSTRAINT fk_card_user FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
            CONSTRAINT fk_card_quiz FOREIGN KEY(quiz_id) REFERENCES quiz_sessions(quiz_id) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci""",
        """CREATE TABLE IF NOT EXISTS learning_events (
            user_id BIGINT UNSIGNED NOT NULL, card_id VARCHAR(64) NOT NULL, version INT NOT NULL,
            source VARCHAR(16) NOT NULL, event_json JSON NOT NULL, created_at DATETIME(6) NOT NULL,
            PRIMARY KEY(user_id,card_id,version), KEY idx_learning_day(user_id,created_at),
            CONSTRAINT fk_event_card FOREIGN KEY(card_id) REFERENCES learning_cards(card_id) ON DELETE CASCADE,
            CONSTRAINT fk_event_user FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci""",
    ],
    10: [
        """CREATE TABLE IF NOT EXISTS learning_notebooks (
            notebook_id VARCHAR(64) NOT NULL PRIMARY KEY, user_id BIGINT UNSIGNED NOT NULL,
            name VARCHAR(80) NOT NULL, name_key CHAR(64) NOT NULL, version INT NOT NULL DEFAULT 1,
            created_at DATETIME(6) NOT NULL, updated_at DATETIME(6) NOT NULL,
            UNIQUE KEY idx_notebook_name(user_id,name_key), UNIQUE KEY idx_notebook_owner(notebook_id,user_id),
            CONSTRAINT fk_notebook_user FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci""",
        """CREATE TABLE IF NOT EXISTS learning_notebook_items (
            notebook_id VARCHAR(64) NOT NULL, user_id BIGINT UNSIGNED NOT NULL,
            quiz_id VARCHAR(64) NOT NULL, question_id VARCHAR(64) NOT NULL, created_at DATETIME(6) NOT NULL,
            PRIMARY KEY(notebook_id,user_id,quiz_id,question_id),
            CONSTRAINT fk_notebook_item_owner FOREIGN KEY(notebook_id,user_id)
                REFERENCES learning_notebooks(notebook_id,user_id) ON DELETE CASCADE,
            CONSTRAINT fk_notebook_item_question FOREIGN KEY(user_id,quiz_id,question_id)
                REFERENCES learning_cards(user_id,quiz_id,question_id) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci""",
    ],
    11: ["""CREATE TABLE IF NOT EXISTS quiz_learning_maps (
        user_id BIGINT UNSIGNED NOT NULL, quiz_id VARCHAR(64) NOT NULL,
        source_hash CHAR(64) NOT NULL, graph_json JSON NOT NULL, updated_at DATETIME NOT NULL,
        PRIMARY KEY(user_id,quiz_id),
        CONSTRAINT fk_study_map_user FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
        CONSTRAINT fk_study_map_quiz FOREIGN KEY(quiz_id) REFERENCES quiz_sessions(quiz_id) ON DELETE CASCADE
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci"""],
    12: ["""CREATE TABLE IF NOT EXISTS quiz_source_context (
        quiz_id VARCHAR(64) NOT NULL PRIMARY KEY, user_id BIGINT UNSIGNED NOT NULL,
        context_json JSON NOT NULL,
        CONSTRAINT fk_quiz_context_quiz FOREIGN KEY(quiz_id) REFERENCES quiz_sessions(quiz_id) ON DELETE CASCADE,
        CONSTRAINT fk_quiz_context_user FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci"""],
    13: ["""CREATE TABLE IF NOT EXISTS quiz_image_assets (
        asset_id VARCHAR(64) NOT NULL PRIMARY KEY, user_id BIGINT UNSIGNED NOT NULL,
        quiz_id VARCHAR(64) NOT NULL, question_id VARCHAR(64) NOT NULL, task_id VARCHAR(64) NOT NULL,
        object_key VARCHAR(512) NOT NULL, state VARCHAR(16) NOT NULL DEFAULT 'pending',
        reserved_day DATE NULL, metadata_json JSON NULL, error_code VARCHAR(64) NULL,
        doc_id VARCHAR(64) NULL, doc_revision INT NULL,
        created_at DATETIME NOT NULL, updated_at DATETIME NOT NULL,
        UNIQUE KEY idx_quiz_image_question(quiz_id,question_id), KEY idx_image_quota(user_id,reserved_day),
        KEY idx_image_task(task_id), KEY idx_image_cleanup(state,updated_at),
        CONSTRAINT fk_image_asset_user FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
        CONSTRAINT fk_image_asset_quiz FOREIGN KEY(quiz_id) REFERENCES quiz_sessions(quiz_id) ON DELETE CASCADE
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci"""],
    14: [
        """CREATE TABLE IF NOT EXISTS tutor_sessions (
            session_id VARCHAR(64) NOT NULL PRIMARY KEY, user_id BIGINT UNSIGNED NOT NULL,
            creation_key VARCHAR(100) NOT NULL, fingerprint CHAR(64) NOT NULL, config_json JSON NOT NULL,
            version INT NOT NULL DEFAULT 0, pending_task_id VARCHAR(64) NULL,
            created_at DATETIME NOT NULL, updated_at DATETIME NOT NULL,
            UNIQUE KEY idx_tutor_creation(user_id,creation_key), UNIQUE KEY idx_tutor_owner(session_id,user_id),
            CONSTRAINT fk_tutor_user FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci""",
        """CREATE TABLE IF NOT EXISTS tutor_turns (
            session_id VARCHAR(64) NOT NULL, user_id BIGINT UNSIGNED NOT NULL, turn_number INT NOT NULL,
            task_id VARCHAR(64) NOT NULL, learner_text TEXT NOT NULL, response_json JSON NOT NULL, created_at DATETIME NOT NULL,
            PRIMARY KEY(session_id,turn_number), UNIQUE KEY idx_tutor_task(task_id),
            CONSTRAINT fk_tutor_turn_owner FOREIGN KEY(session_id,user_id) REFERENCES tutor_sessions(session_id,user_id) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci""",
    ],
    15: [
        """CREATE TABLE IF NOT EXISTS learning_path_settings (
            user_id BIGINT UNSIGNED NOT NULL PRIMARY KEY, version INT NOT NULL DEFAULT 1,
            edges_json JSON NOT NULL, updated_at DATETIME(6) NOT NULL,
            CONSTRAINT fk_path_user FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci""",
        """CREATE TABLE IF NOT EXISTS learning_plans (
            plan_id VARCHAR(64) NOT NULL PRIMARY KEY, user_id BIGINT UNSIGNED NOT NULL,
            creation_key VARCHAR(100) NOT NULL, request_hash CHAR(64) NOT NULL,
            plan_json JSON NOT NULL, created_at DATETIME(6) NOT NULL,
            UNIQUE KEY idx_plan_request(user_id,creation_key), UNIQUE KEY idx_plan_owner(plan_id,user_id),
            KEY idx_plan_recent(user_id,created_at),
            CONSTRAINT fk_plan_user FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci""",
        """CREATE TABLE IF NOT EXISTS learning_plan_checks (
            plan_id VARCHAR(64) NOT NULL, user_id BIGINT UNSIGNED NOT NULL, item_id VARCHAR(100) NOT NULL,
            created_at DATETIME(6) NOT NULL, PRIMARY KEY(plan_id,user_id,item_id),
            CONSTRAINT fk_plan_check_owner FOREIGN KEY(plan_id,user_id) REFERENCES learning_plans(plan_id,user_id) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci""",
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
