from unittest.mock import AsyncMock, patch

import pytest

from app.core.config import Settings


def test_default_startup_never_initializes_a_database():
    assert Settings(_env_file=None).mysql_auto_init is False


@pytest.mark.asyncio
async def test_normal_connection_does_not_issue_schema_statements():
    from app.core import db

    with patch.object(db, "_pool", None), patch.object(db.aiomysql, "create_pool", new_callable=AsyncMock) as pool:
        await db.connect_mysql()
    assert pool.await_count == 1
    assert pool.call_args.kwargs["autocommit"] is True
    assert pool.call_args.kwargs["init_command"] == "SET time_zone = '+00:00'"
