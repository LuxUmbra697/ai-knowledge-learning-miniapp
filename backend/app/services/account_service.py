"""Independent H5 accounts. WeChat identities are never inferred or merged."""

import asyncio
import hashlib
import hmac
import secrets

import aiomysql
from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.auth import create_token
from app.core.db import get_mysql_pool
from app.core.config import get_settings
from app.models.user import LoginResponse, UserBrief

_password_slots = asyncio.Semaphore(2)


class AccountCredentials(BaseModel):
    model_config = ConfigDict(extra="forbid")
    username: str = Field(min_length=3, max_length=40, pattern=r"^[a-zA-Z0-9_.-]+$")
    password: str = Field(min_length=10, max_length=128)
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


async def check_login_rate(address: str, username: str):
    pool = get_mysql_pool()
    if pool is None:
        raise HTTPException(503, "账号服务暂时不可用")
    # Buckets retain no raw IP or username, and are shared across API restarts.
    buckets = [hmac.new(get_settings().jwt_secret.encode(), value.encode(), "sha256").hexdigest()
               for value in (f"ip:{address}", f"account:{address}:{username}")]
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            for bucket, limit in zip(buckets, (60, 12)):
                await cur.execute("INSERT INTO auth_rate_limits (bucket,hits,expires_at) VALUES (%s,1,DATE_ADD(UTC_TIMESTAMP(), INTERVAL 10 MINUTE)) "
                                  "ON DUPLICATE KEY UPDATE hits=IF(expires_at<UTC_TIMESTAMP(),1,hits+1), "
                                  "expires_at=IF(expires_at<UTC_TIMESTAMP(),DATE_ADD(UTC_TIMESTAMP(),INTERVAL 10 MINUTE),expires_at)", (bucket,))
                await cur.execute("SELECT hits FROM auth_rate_limits WHERE bucket=%s", (bucket,))
                if (await cur.fetchone())[0] > limit:
                    raise HTTPException(429, "登录尝试过于频繁，请十分钟后再试")
            await cur.execute("DELETE FROM auth_rate_limits WHERE expires_at<DATE_SUB(UTC_TIMESTAMP(),INTERVAL 1 DAY) LIMIT 100")


async def authenticate(credentials: AccountCredentials, register: bool, address: str) -> LoginResponse:
    await check_login_rate(address, credentials.username)
    pool = get_mysql_pool()
    async with _password_slots:
        if register:
            password_hash = await asyncio.to_thread(hash_password, credentials.password)
            async with pool.acquire() as conn:
                await conn.begin()
                try:
                    async with conn.cursor() as cur:
                        await cur.execute("INSERT INTO users(openid,nickname) VALUES(NULL,%s)", (credentials.nickname,))
                        user_id = cur.lastrowid
                        await cur.execute("INSERT INTO account_credentials(username,user_id,password_hash) VALUES(%s,%s,%s)",
                                          (credentials.username, user_id, password_hash))
                    await conn.commit()
                except aiomysql.IntegrityError:
                    await conn.rollback()
                    raise HTTPException(409, "该账号名称已被使用") from None
                except BaseException:
                    await conn.rollback()
                    raise
            user = UserBrief(id=user_id, nickname=credentials.nickname, avatar_url="", total_xp=0)
        else:
            async with pool.acquire() as conn:
                async with conn.cursor(aiomysql.DictCursor) as cur:
                    await cur.execute("SELECT c.password_hash,u.id,u.nickname,u.avatar_url,u.total_xp FROM account_credentials c JOIN users u ON u.id=c.user_id WHERE c.username=%s", (credentials.username,))
                    row = await cur.fetchone()
            if row is None:
                await asyncio.to_thread(hash_password, credentials.password)
                raise HTTPException(401, "账号或密码不正确")
            if not await asyncio.to_thread(verify_password, credentials.password, row["password_hash"]):
                raise HTTPException(401, "账号或密码不正确")
            user = UserBrief.model_validate(row)
    return LoginResponse(token=create_token(user.id, ""), user=user)
