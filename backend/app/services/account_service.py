"""Shared password accounts. WeChat identities require explicit verified linking."""

import asyncio
import hashlib
import hmac
import secrets

import aiomysql
from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.db import get_mysql_pool
from app.core.config import get_settings
from app.models.user import LoginResponse

_password_slots = asyncio.Semaphore(2)


class AccountCredentials(BaseModel):
    model_config = ConfigDict(extra="forbid")
    username: str = Field(min_length=3, max_length=40, pattern=r"^[a-zA-Z0-9_.-]+$")
    password: str = Field(min_length=10, max_length=128, repr=False)
    nickname: str = Field(default="学习者", min_length=1, max_length=40)

    @field_validator("username")
    @classmethod
    def normalize_username(cls, value):
        return value.lower()


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=16384, r=8, p=1, dklen=32)
    return f"scrypt$16384$8$1${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algorithm, n, r, p, salt, digest = stored.split("$")
        if (algorithm, n, r, p) != ("scrypt", "16384", "8", "1"):
            return False
        actual = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=1, dklen=32)
        return hmac.compare_digest(actual, bytes.fromhex(digest))
    except (ValueError, TypeError):
        return False


async def check_login_rate(address: str, username: str, *, scope='login', limits=(60, 12)):
    pool = get_mysql_pool()
    if pool is None:
        raise HTTPException(503, "账号服务暂时不可用")
    # Buckets retain no raw IP or username, and are shared across API restarts.
    buckets = [hmac.new(get_settings().jwt_secret.encode(), value.encode(), "sha256").hexdigest()
               for value in (f"{scope}:ip:{address}", f"{scope}:account:{address}:{username}")]
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            for bucket, limit in zip(buckets, limits):
                await cur.execute("INSERT INTO auth_rate_limits (bucket,hits,expires_at) VALUES (%s,1,DATE_ADD(UTC_TIMESTAMP(), INTERVAL 10 MINUTE)) "
                                  "ON DUPLICATE KEY UPDATE hits=IF(expires_at<UTC_TIMESTAMP(),1,hits+1), "
                                  "expires_at=IF(expires_at<UTC_TIMESTAMP(),DATE_ADD(UTC_TIMESTAMP(),INTERVAL 10 MINUTE),expires_at)", (bucket,))
                await cur.execute("SELECT hits FROM auth_rate_limits WHERE bucket=%s", (bucket,))
                if (await cur.fetchone())[0] > limit:
                    raise HTTPException(429, "登录尝试过于频繁，请十分钟后再试")
            await cur.execute("DELETE FROM auth_rate_limits WHERE expires_at<DATE_SUB(UTC_TIMESTAMP(),INTERVAL 1 DAY) LIMIT 100")


async def authenticate(credentials: AccountCredentials, register: bool, address: str) -> LoginResponse:
    from app.services.identity_service import rotate_recovery, check_password, login_result
    from app.repositories.rag_index_repository import transaction
    await check_login_rate(address, credentials.username)
    recovery = None
    if register:
        async with _password_slots:
            password_hash = await asyncio.to_thread(hash_password, credentials.password)
    try:
        async with transaction() as cur:
            if register:
                await cur.execute('INSERT INTO users(openid,nickname) VALUES(NULL,%s)', (credentials.nickname,))
                user_id = cur.lastrowid
                await cur.execute('INSERT INTO account_credentials(username,user_id,password_hash) VALUES(%s,%s,%s)',
                                  (credentials.username, user_id, password_hash))
                recovery = await rotate_recovery(cur, user_id)
            else:
                user_id = await check_password(cur, credentials)
            return LoginResponse.model_validate(await login_result(cur, user_id, recovery))
    except aiomysql.IntegrityError:
        raise HTTPException(409, '该账号名称已被使用') from None
