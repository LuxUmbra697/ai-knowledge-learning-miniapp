import importlib.util
from pathlib import Path
from unittest.mock import Mock
import pytest

spec = importlib.util.spec_from_file_location('local_mysql', Path(__file__).resolve().parents[2] / 'scripts/local_mysql.py')
mysql = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mysql)


def test_shutdown_refuses_a_different_data_directory(monkeypatch, tmp_path):
    connection = Mock()
    cursor = Mock()
    connection.cursor.return_value.__enter__ = Mock(return_value=cursor)
    connection.cursor.return_value.__exit__ = Mock(return_value=False)
    cursor.fetchone.return_value = (str(tmp_path / 'other-project'), '8.0.45')
    monkeypatch.setattr(mysql.pymysql, 'connect', lambda **kwargs: connection)
    monkeypatch.setattr(mysql, 'port_open', lambda: True)
    with pytest.raises(RuntimeError, match='refusing'):
        mysql.stop()
    assert all(call.args[0] != 'SHUTDOWN' for call in cursor.execute.call_args_list)
    connection.close.assert_called_once()


def test_existing_unknown_directory_is_not_initialized(monkeypatch, tmp_path):
    binary = tmp_path / 'mysqld'
    binary.write_text('not executed', encoding='utf8')
    data = tmp_path / 'data'
    data.mkdir()
    (data / 'important').write_text('preserve', encoding='utf8')
    monkeypatch.setattr(mysql, 'PRIVATE', tmp_path)
    monkeypatch.setattr(mysql, 'DATA', data)
    monkeypatch.setattr(mysql, 'port_open', lambda: False)
    run = Mock()
    monkeypatch.setattr(mysql.subprocess, 'run', run)
    with pytest.raises(RuntimeError, match='no files were removed'):
        mysql.start(str(binary))
    run.assert_not_called()
    assert (data / 'important').read_text(encoding='utf8') == 'preserve'
