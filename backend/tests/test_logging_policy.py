"""Logging regressions run in child processes to isolate global logger settings."""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from app.core.config import Settings
from pydantic import ValidationError

ROOT = Path(__file__).resolve().parents[2]


def execute(code):
    env = {**os.environ, 'AI_LEARN_ENV_FILE': '', 'APP_ENV': 'test',
           'MYSQL_AUTO_INIT': 'false', 'WORKER_ENABLED': 'false',
           'PYTHONPATH': str(ROOT / 'backend')}
    result = subprocess.run([sys.executable, '-c', code], env=env, cwd=ROOT,
                            capture_output=True, text=True, timeout=20, check=False)
    assert result.returncode == 0, result.stderr
    return result.stdout + result.stderr


def test_warning_level_filters_existing_structlog_and_standard_library_loggers():
    output = execute('''
import logging
import structlog
from app.core.logging import configure_logging
existing = structlog.get_logger('existing')
configure_logging('WARNING')
configure_logging('WARNING')
existing.debug('hidden_debug')
existing.info('hidden_info')
logging.getLogger('httpx').info('hidden_request')
existing.warning('worker_poll_failed', error_type='ConnectionError')
existing.error('unhandled_exception', trace_id='test-trace')
logging.getLogger('dependency').warning('dependency_warning')
''')
    assert 'hidden_' not in output
    assert output.count('worker_poll_failed') == 1
    assert output.count('dependency_warning') == 1
    events = [json.loads(line) for line in output.splitlines() if line.startswith('{')]
    assert [(row['event'], row['level']) for row in events] == [
        ('worker_poll_failed', 'warning'), ('unhandled_exception', 'error')]
    assert events[1]['trace_id'] == 'test-trace'


def test_info_can_be_enabled_for_bounded_diagnosis():
    output = execute('''
import structlog
from app.core.logging import configure_logging
configure_logging('INFO')
structlog.get_logger().info('diagnostic_enabled')
structlog.get_logger().debug('hidden_debug')
''')
    assert 'diagnostic_enabled' in output and 'hidden_debug' not in output


def test_application_startup_applies_setting_before_database_and_worker():
    output = execute('''
import asyncio
from unittest.mock import AsyncMock
import structlog
from app import main
from app.core.config import Settings
main.get_settings = lambda: Settings(_env_file=None, log_level='WARNING', worker_enabled=False)
main.connect_mysql = AsyncMock()
main.close_mysql_pool = AsyncMock()
async def exercise():
    async with main.lifespan(main.app):
        structlog.get_logger().info('hidden_lifespan_info')
        structlog.get_logger().warning('startup_warning_retained')
    main.connect_mysql.assert_awaited_once()
    main.close_mysql_pool.assert_awaited_once()
asyncio.run(exercise())
''')
    assert 'hidden_lifespan_info' not in output
    assert 'app_starting' not in output and 'app_shutting_down' not in output
    assert output.count('startup_warning_retained') == 1


@pytest.mark.parametrize('value', ['ALL', 'OFF', 'NOTSET', 'WARNIG'])
def test_invalid_log_levels_fail_closed(value):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, log_level=value)


def test_lowercase_log_level_is_normalized():
    assert Settings(_env_file=None, log_level='warning').log_level == 'WARNING'
