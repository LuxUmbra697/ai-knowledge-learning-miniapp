"""一次性执行 MySQL 建库建表初始化。"""

from __future__ import annotations

import asyncio

from app.core.db import close_mysql_pool, init_mysql


async def main() -> None:
    await init_mysql()
    await close_mysql_pool()


if __name__ == "__main__":
    asyncio.run(main())