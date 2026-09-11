"""Start an isolated local API; paid provider access requires --with-models."""

import argparse
import asyncio
import os
from pathlib import Path
import secrets
import sys

from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]


def configure(with_models=False):
    config = dotenv_values(ROOT / "backend/.env") if with_models else {}
    for key, value in config.items():
        if value is not None:
            os.environ[key] = value
    private = ROOT / ".local"
    private.mkdir(exist_ok=True)
    signing_key = private / "local-jwt.key"
    if not signing_key.exists():
        signing_key.write_text(secrets.token_urlsafe(48), encoding="ascii")
    os.environ.update(AI_LEARN_ENV_FILE="", MYSQL_HOST="127.0.0.1", MYSQL_PORT="13308",
                      MYSQL_USER="root", MYSQL_PASSWORD="", MYSQL_DATABASE="ai_learn_local",
                      MYSQL_AUTO_INIT="false", MYSQL_POOL_MAXSIZE="3", MYSQL_POOL_MINSIZE="1",
                      JWT_SECRET=signing_key.read_text(encoding="ascii"), APP_DEBUG="true",
                      CHROMA_PERSIST_DIR=str(private / "chroma"), KB_UPLOAD_DIR=str(private / "uploads"),
                      ENABLE_WEB_SEARCH="false", COS_UPLOAD_PREFIX="ai-learn-local-test/",
                      ANONYMIZED_TELEMETRY="false")
    sys.path.insert(0, str(ROOT / "backend"))


async def initialize():
    from app.core.db import init_mysql, close_mysql_pool
    from app.core.migrations import migrate
    try:
        await init_mysql()
        await migrate()
    finally:
        await close_mysql_pool()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--with-models", action="store_true")
    parser.add_argument("--initialize", action="store_true")
    parser.add_argument("--port", type=int, default=18081)
    args = parser.parse_args()
    configure(args.with_models)
    if args.initialize:
        asyncio.run(initialize())
    else:
        import uvicorn
        uvicorn.run("app.main:app", host="127.0.0.1", port=args.port, access_log=False)
