"""Run deterministic tests without loading dotenv or reaching external services."""

import os
import socket
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.core.config import Settings  # noqa: E402

Settings.model_config["env_file"] = None
for field in Settings.model_fields:
    os.environ.pop(field.upper(), None)
os.environ.update(MYSQL_AUTO_INIT="false", ENABLE_WEB_SEARCH="false", MYSQL_PORT="1",
                  JWT_SECRET="offline-test-secret-with-at-least-32-characters", ANONYMIZED_TELEMETRY="false",
                  AI_LEARN_ENV_FILE="", APP_ENV="test")

_connect = socket.socket.connect


def isolated_connect(sock, address):
    # Windows asyncio uses loopback socket pairs even for in-process ASGI tests.
    if isinstance(address, tuple) and address[0] not in ("127.0.0.1", "::1"):
        raise RuntimeError("External network disabled in deterministic tests")
    return _connect(sock, address)


socket.socket.connect = isolated_connect

if __name__ == "__main__":
    import pytest

    temporary = ROOT / ".local/tests" / uuid.uuid4().hex
    temporary.parent.mkdir(parents=True, exist_ok=True)
    arguments = [str(ROOT / 'backend/tests'), *(sys.argv[1:] or ['-q', '--tb=short'])]
    raise SystemExit(pytest.main([*arguments, f"--basetemp={temporary}"]))
