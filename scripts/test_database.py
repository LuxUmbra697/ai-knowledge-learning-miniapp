"""Deterministic integration tests against the isolated loopback MySQL, never dotenv."""
import sys
from pathlib import Path
from run_local import configure

configure(False)

if __name__ == '__main__':
    import pytest
    raise SystemExit(pytest.main([str(Path(__file__).resolve().parents[1] / 'backend/integration'), '-q', '--tb=short', *sys.argv[1:]]))
