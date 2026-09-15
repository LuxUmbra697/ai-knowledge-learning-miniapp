"""Run from backend: python -m scripts.migrate [--initialize-new]."""

import argparse
import asyncio

from app.core.db import close_mysql_pool, connect_mysql, init_mysql
from app.core.migrations import migrate


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--initialize-new", action="store_true")
    args = parser.parse_args()
    try:
        await (init_mysql() if args.initialize_new else connect_mysql())
        await migrate()
        print("Migrations complete")
    finally:
        await close_mysql_pool()


if __name__ == "__main__":
    asyncio.run(main())
