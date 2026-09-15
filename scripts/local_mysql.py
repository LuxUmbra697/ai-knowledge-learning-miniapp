"""Manage only this workspace's isolated loopback MySQL data directory, never a cloud database."""
import argparse
import os
from pathlib import Path
import shutil
import socket
import subprocess
import time

import pymysql

ROOT = Path(__file__).resolve().parents[1]
PRIVATE = ROOT / '.local/mysql'
DATA = PRIVATE / 'data'
PORT = 23308


def port_open():
    try:
        with socket.create_connection(('127.0.0.1', PORT), timeout=1):
            return True
    except OSError:
        return False


def connect_owned():
    connection = pymysql.connect(host='127.0.0.1', port=PORT, user='root', password='',
                                 connect_timeout=3, read_timeout=3, autocommit=True)
    try:
        with connection.cursor() as cursor:
            cursor.execute('SELECT @@datadir, VERSION()')
            directory, version = cursor.fetchone()
            if Path(directory).resolve() != DATA.resolve() or not version.startswith('8.'):
                raise RuntimeError('Port 23308 is not this workspace MySQL 8 instance; refusing to alter it')
        return connection
    except Exception:
        connection.close()
        raise


def status():
    connection = connect_owned()
    connection.close()
    print('Isolated MySQL ready on 127.0.0.1:23308')


def start(executable):
    if port_open():
        return status()
    binary = str(Path(executable).resolve()) if executable else shutil.which('mysqld')
    if not binary or not Path(binary).is_file():
        raise RuntimeError('Install MySQL 8, add its bin directory to PATH, or pass --mysqld with the mysqld executable')
    PRIVATE.mkdir(parents=True, exist_ok=True)
    if not DATA.exists() or not any(DATA.iterdir()):
        DATA.mkdir(exist_ok=True)
        with (PRIVATE / 'initialize.log').open('ab') as log:
            subprocess.run([binary, '--no-defaults', '--initialize-insecure', f'--datadir={DATA}'], stdout=log, stderr=log,
                           check=True, timeout=120, creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
    elif not (DATA / 'mysql').exists():
        raise RuntimeError('Existing nonempty data directory is not recognized; no files were removed or initialized')
    with (PRIVATE / 'launcher.log').open('ab') as log:
        subprocess.Popen([binary, '--no-defaults', f'--datadir={DATA}', f'--port={PORT}', '--bind-address=127.0.0.1',
                          '--mysqlx=0', '--max-connections=30', '--innodb-buffer-pool-size=64M',
                          f'--log-error={PRIVATE / "mysql.log"}', f'--pid-file={PRIVATE / "mysql.pid"}',
                          f'--socket={PRIVATE / "mysql.sock"}'], stdout=log, stderr=log, cwd=ROOT,
                         creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
    for _ in range(40):
        if port_open():
            return status()
        time.sleep(1)
    raise RuntimeError('Local MySQL did not become ready; inspect .local/mysql/launcher.log')


def stop():
    if not port_open():
        print('Isolated MySQL is already stopped')
        return
    connection = connect_owned()
    try:
        with connection.cursor() as cursor:
            cursor.execute('SHUTDOWN')
    finally:
        connection.close()
    print('Isolated MySQL stopped; its data directory is preserved')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('operation', choices=['start', 'status', 'stop'])
    parser.add_argument('--mysqld')
    args = parser.parse_args()
    try:
        if args.operation == 'start':
            start(args.mysqld)
        elif args.operation == 'stop':
            stop()
        else:
            status()
    except (RuntimeError, pymysql.MySQLError, subprocess.SubprocessError) as error:
        # Connector exceptions must not expose credentials or a remote connection URL.
        raise SystemExit(str(error) if isinstance(error, RuntimeError) else f'Local MySQL operation failed: {type(error).__name__}') from None
