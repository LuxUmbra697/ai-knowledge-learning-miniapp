"""Explicit owned-schema operations. Never drops schemas or silently adopts an existing database."""
import argparse
import asyncio
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

from dotenv import dotenv_values
import pymysql

ROOT = Path(__file__).resolve().parents[1]
BACKUPS = ROOT / '.local/backups'


def identifier(value):
    if not re.fullmatch(r'[A-Za-z0-9_]{1,64}', value or ''):
        raise ValueError('Unsafe schema identifier')
    return value


def connect(config):
    return pymysql.connect(host=config['MYSQL_HOST'], port=int(config.get('MYSQL_PORT', '3306')),
                           user=config['MYSQL_USER'], password=config['MYSQL_PASSWORD'],
                           charset='utf8mb4', autocommit=True, connect_timeout=10, read_timeout=30)


def inventory(connection, schema):
    identifier(schema)
    with connection.cursor() as cursor:
        cursor.execute('SELECT SCHEMA_NAME FROM information_schema.SCHEMATA WHERE SCHEMA_NAME=%s', (schema,))
        exists = cursor.fetchone() is not None
        cursor.execute('SELECT TABLE_NAME FROM information_schema.TABLES WHERE TABLE_SCHEMA=%s ORDER BY TABLE_NAME', (schema,))
        tables = [row[0] for row in cursor.fetchall()]
        versions = []
        if 'schema_migrations' in tables:
            cursor.execute(f'SELECT version FROM `{schema}`.schema_migrations ORDER BY version')
            versions = [row[0] for row in cursor.fetchall()]
        return {'exists': exists, 'tables': tables, 'versions': versions}


def create_absent(connection, schema):
    identifier(schema)
    if inventory(connection, schema)['exists']:
        raise RuntimeError('Schema already exists; refusing empty-schema initialization or restore')
    with connection.cursor() as cursor:
        # No IF NOT EXISTS: a concurrent creator must stop us, not make us adopt its database.
        cursor.execute(f'CREATE DATABASE `{schema}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci')


def fresh_inventory(config, schema):
    # DDL or restore can outlive an idle metadata connection; never repeat writes to refresh evidence.
    connection = connect(config)
    try:
        return inventory(connection, schema)
    finally:
        connection.close()


async def initialize_schema(config, schema):
    sys.path.insert(0, str(ROOT / 'backend'))
    os.environ.update({key: value for key, value in config.items() if value is not None})
    os.environ.update(AI_LEARN_ENV_FILE='', MYSQL_DATABASE=schema, MYSQL_AUTO_INIT='false',
                      MYSQL_POOL_MINSIZE='1', MYSQL_POOL_MAXSIZE='2', ANONYMIZED_TELEMETRY='false')
    from app.core.config import get_settings
    from app.core.db import connect_mysql, close_mysql_pool, get_mysql_pool, SCHEMA_STATEMENTS
    from app.core.migrations import migrate
    get_settings.cache_clear()
    try:
        await connect_mysql()
        async with get_mysql_pool().acquire() as connection:
            async with connection.cursor() as cursor:
                for statement in SCHEMA_STATEMENTS:
                    await cursor.execute(statement)
        await migrate()
    finally:
        await close_mysql_pool()


def option_value(value):
    if '\n' in value or '\r' in value or '\x00' in value:
        raise ValueError('Invalid newline in database client configuration')
    return '"' + value.replace('\\', '\\\\').replace('"', '\\"') + '"'


def run_client(binary, config, arguments, *, stdin=None, stdout=None):
    private = ROOT / '.local/db-client'
    private.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(prefix='client-', suffix='.cnf', dir=private)
    try:
        with os.fdopen(descriptor, 'w', encoding='utf8') as options:
            options.write('[client]\n')
            for key, value in [('host', config['MYSQL_HOST']), ('port', config.get('MYSQL_PORT', '3306')),
                               ('user', config['MYSQL_USER']), ('password', config['MYSQL_PASSWORD'])]:
                options.write(key + '=' + option_value(str(value)) + '\n')
        result = subprocess.run([str(binary), '--defaults-extra-file=' + name, *arguments], stdin=stdin,
                                stdout=stdout, stderr=subprocess.PIPE, timeout=180,
                                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        if result.returncode:
            raise RuntimeError(f'Database client failed with exit {result.returncode}; raw diagnostics withheld')
    finally:
        Path(name).unlink(missing_ok=True)


def backup(config, schema, binary):
    from datetime import datetime, timezone
    BACKUPS.mkdir(parents=True, exist_ok=True)
    name = schema + '-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ') + '.sql'
    destination = BACKUPS / name
    with destination.open('xb') as output:
        run_client(binary, config, ['--single-transaction', '--skip-lock-tables', '--no-tablespaces',
            '--set-gtid-purged=OFF', '--column-statistics=0', '--hex-blob', '--skip-comments', schema], stdout=output)
    manifest = {'schema': schema, 'sha256': hashlib.sha256(destination.read_bytes()).hexdigest(),
                'bytes': destination.stat().st_size, 'format': 'mysqldump-single-schema-v1'}
    destination.with_suffix('.json').write_text(json.dumps(manifest, indent=2), encoding='utf8')
    return destination


def verified_backup(filename):
    path = Path(filename).resolve()
    if not path.is_relative_to(BACKUPS.resolve()) or path.suffix != '.sql':
        raise ValueError('Restore only accepts this project private backup directory')
    manifest = json.loads(path.with_suffix('.json').read_text(encoding='utf8'))
    if manifest.get('format') != 'mysqldump-single-schema-v1' or hashlib.sha256(path.read_bytes()).hexdigest() != manifest['sha256']:
        raise ValueError('Backup integrity check failed')
    return path


def execute(args):
    config = dotenv_values(args.env)
    schema = identifier(config.get('MYSQL_DATABASE'))
    if args.rehearsal:
        if not re.fullmatch(r'ai_learn_rehearsal_[a-f0-9]{12}', args.rehearsal):
            raise ValueError('Rehearsals require an isolated ai_learn_rehearsal_<12 hex> schema')
        schema = args.rehearsal
    connection = connect(config)
    try:
        before = inventory(connection, schema)
        if args.mode == 'inspect':
            print(json.dumps({'schema_exists': before['exists'], 'table_count': len(before['tables']), 'migration_versions': before['versions']}))
        elif args.mode == 'initialize-empty':
            create_absent(connection, schema)
            asyncio.run(initialize_schema(config, schema))
            after = fresh_inventory(config, schema)
            print(json.dumps({'initialized': True, 'table_count': len(after['tables']), 'versions': after['versions']}))
        elif args.mode == 'backup':
            if not before['exists'] or not before['versions']:
                raise RuntimeError('Backup requires an existing versioned learning schema')
            if not args.client:
                raise ValueError('Pass --client with the MySQL 8 mysqldump binary')
            path = backup(config, schema, args.client)
            print(json.dumps({'backup': str(path.relative_to(ROOT)), 'bytes': path.stat().st_size}))
        elif args.mode == 'restore-rehearsal':
            if not args.rehearsal or not args.client or not args.backup:
                raise ValueError('Restore requires --rehearsal, --client mysql and --backup')
            path = verified_backup(args.backup)
            create_absent(connection, schema)
            with path.open('rb') as source:
                run_client(args.client, config, ['--binary-mode', schema], stdin=source, stdout=subprocess.DEVNULL)
            after = fresh_inventory(config, schema)
            print(json.dumps({'restored': True, 'table_count': len(after['tables']), 'versions': after['versions']}))
    finally:
        connection.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('mode', choices=['inspect', 'initialize-empty', 'backup', 'restore-rehearsal'])
    parser.add_argument('--env', required=True)
    parser.add_argument('--rehearsal')
    parser.add_argument('--client')
    parser.add_argument('--backup')
    try:
        execute(parser.parse_args())
    except (RuntimeError, ValueError, KeyError, OSError, pymysql.MySQLError, subprocess.SubprocessError) as error:
        raise SystemExit(str(error) if isinstance(error, (RuntimeError, ValueError)) else
                         f'Database operation failed: {type(error).__name__}; configuration values withheld') from None
