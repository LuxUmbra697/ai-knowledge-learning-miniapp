"""Deterministic integration tests against the isolated loopback MySQL, never dotenv."""
import sys
import os
import asyncio
from pathlib import Path
from run_local import configure
from run_local import initialize

configure(False)
os.environ['MYSQL_DATABASE'] = 'ai_learn_test'

if __name__ == '__main__':
    import pytest
    asyncio.run(initialize())
    raise SystemExit(pytest.main([str(Path(__file__).resolve().parents[1] / 'backend/integration'), '-q', '--tb=short', *sys.argv[1:]]))
