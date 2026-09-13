"""Subprocess restart probe, restricted to the loopback test database and synthetic jobs."""
import asyncio
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
from run_local import configure

configure(False)
os.environ['MYSQL_DATABASE'] = 'ai_learn_test'

from app.core.db import connect_mysql, close_mysql_pool
from app.worker import run_once


async def probe(context):
    if context.checkpoints.get('restart_probe'):
        return {'recovered': True, 'external_calls': 0}
    await context.checkpoint('restart_probe', {'synthetic': True})
    await asyncio.sleep(90)
    return {'recovered': False}


async def main():
    await connect_mysql()
    try:
        await run_once({'answer': probe})
    finally:
        await close_mysql_pool()


if __name__ == '__main__':
    asyncio.run(main())
