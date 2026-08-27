"""腾讯云 COS 对象存储服务 - 用于持久化保存 AI 生成的题目配图"""

from __future__ import annotations

import asyncio
from functools import lru_cache

import structlog
from qcloud_cos import CosConfig, CosS3Client

from app.core.config import get_settings

logger = structlog.get_logger()


@lru_cache
def _get_cos_client() -> CosS3Client:
    settings = get_settings()
    config = CosConfig(
        Region=settings.cos_region,
        SecretId=settings.cos_secret_id,
        SecretKey=settings.cos_secret_key,
        Scheme="https",
    )
    return CosS3Client(config)


def _build_public_url(key: str) -> str:
    settings = get_settings()
    if settings.cos_domain:
        return f"https://{settings.cos_domain}/{key}"
    return f"https://{settings.cos_bucket}.cos.{settings.cos_region}.myqcloud.com/{key}"


def _put_object_sync(data: bytes, key: str, content_type: str) -> None:
    settings = get_settings()
    client = _get_cos_client()
    client.put_object(
        Bucket=settings.cos_bucket,
        Body=data,
        Key=key,
        ContentType=content_type,
    )


async def upload_image_bytes(data: bytes, key: str, content_type: str = "image/png") -> str:
    """将图片字节流上传到 COS，返回可公开访问的 URL。

    COS SDK 为同步阻塞调用，通过线程池转为异步以避免阻塞事件循环。
    """
    settings = get_settings()
    if not (settings.cos_secret_id and settings.cos_secret_key and settings.cos_bucket and settings.cos_region):
        raise RuntimeError("COS 未配置，无法上传图片")

    await asyncio.to_thread(_put_object_sync, data, key, content_type)
    url = _build_public_url(key)
    logger.info("cos_upload_success", key=key)
    return url
