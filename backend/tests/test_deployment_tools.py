import importlib.util
from pathlib import Path
from unittest.mock import Mock

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('manage_database', ROOT / 'scripts/manage_database.py')
database = importlib.util.module_from_spec(spec)
spec.loader.exec_module(database)


@pytest.mark.parametrize('value', ['other`; DROP DATABASE users; --', '../data', '', 'a' * 65])
def test_schema_identifiers_cannot_be_sql_or_paths(value):
    with pytest.raises(ValueError):
        database.identifier(value)


def test_empty_initialization_never_adopts_existing_schema(monkeypatch):
    connection = Mock()
    monkeypatch.setattr(database, 'inventory', lambda *args: {'exists': True})
    with pytest.raises(RuntimeError, match='already exists'):
        database.create_absent(connection, 'ai_learn_local')
    connection.cursor.assert_not_called()


def test_dump_credentials_are_quoted_and_never_accept_extra_option_lines():
    assert database.option_value('x"\\#;$') == '"x\\"\\\\#;$"'
    with pytest.raises(ValueError):
        database.option_value('password\nhost=other')


def test_restore_cannot_read_outside_private_backups(tmp_path):
    with pytest.raises(ValueError, match='private backup'):
        database.verified_backup(tmp_path / 'untrusted.sql')


def test_production_container_keeps_limits_identity_and_explicit_paid_mode():
    compose = yaml.safe_load((ROOT / 'deploy/compose.yaml').read_text(encoding='utf8'))
    service = compose['services']['studio']
    assert service['environment']['REQUIRE_PAID_MODELS'] == 'true'
    assert service['environment']['APP_DEBUG'] == service['environment']['MYSQL_AUTO_INIT'] == 'false'
    assert service['ports'] == ['127.0.0.1:18083:8000']
    assert service['mem_limit'] == '256m'
    assert service['read_only'] and service['cap_drop'] == ['ALL']
    assert service['networks']['gateway']['aliases'] == ['ai-learn-studio']
    dockerfile = (ROOT / 'deploy/Dockerfile').read_text(encoding='utf8')
    assert 'USER 10001:10001' in dockerfile
    assert 'COPY . .' not in dockerfile and '--require-hashes' in dockerfile
    assert 'ARG PYPI_INDEX_URL=https://pypi.org/simple' in dockerfile
    assert '--trusted-host' not in dockerfile and 'http://' not in dockerfile.split('HEALTHCHECK')[0]
    assert '"--workers", "1"' in dockerfile
