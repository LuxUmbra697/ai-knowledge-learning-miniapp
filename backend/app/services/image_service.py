"""题目配图生成服务

负责：
1. 根据题目内容构建生图 Prompt
2. 调用阿里云百炼 qwen-image-2.0 模型同步生成图片（多题并发）
3. 下载生成的图片并上传至腾讯云 COS，得到永久可访问 URL
4. 应用「每人每天生图次数」限额

生图失败（单张或全部）不应影响出题主流程，因此本模块的对外入口
`generate_images_for_quiz` 永远不会抛出异常。
"""

from __future__ import annotations

import asyncio
import uuid
from typing import Optional

import httpx
import structlog

from app.core.config import get_settings
from app.models.quiz import Question
from app.repositories import image_repository
from app.services.cos_service import upload_image_bytes

logger = structlog.get_logger()

IMAGE_DOWNLOAD_TIMEOUT = 30.0


def _derive_image_base_url(dashscope_base_url: str) -> str:
    """从 OpenAI 兼容模式的 dashscope_base_url 派生原生 DashScope API 地址。

    例如 https://xxx.cn-beijing.maas.aliyuncs.com/compatible-mode/v1
    -> https://xxx.cn-beijing.maas.aliyuncs.com/api/v1
    """
    if dashscope_base_url.endswith("/compatible-mode/v1"):
        return dashscope_base_url[: -len("/compatible-mode/v1")] + "/api/v1"
    return dashscope_base_url


def build_image_prompt(question: Question) -> str:
    """根据题目内容构建生图 Prompt。"""
    return (
        f"为一道学习闯关题目生成配图。知识点：{question.knowledge_point}。"
        f"题目内容：{question.stem}。\n"
        "要求：画面聚焦题目描述的核心主体（如具体的单词实物、动植物、历史场景、地理风貌等），"
        "根据内容自行选择最合适的写实摄影或扁平插画风格，构图简洁、主体突出、色彩明快，"
        "适合作为教学配图；画面中不要出现任何文字、字母、水印或题目答案。"
    )


def _call_image_model_sync(prompt: str) -> str:
    """同步调用 DashScope 千问-文生图模型，返回图片临时 URL（阻塞调用，需在线程中运行）。"""
    import dashscope
    from dashscope import MultiModalConversation

    settings = get_settings()

    base_url = settings.dashscope_image_base_url or _derive_image_base_url(settings.dashscope_base_url)
    if base_url:
        dashscope.base_http_api_url = base_url

    response = MultiModalConversation.call(
        api_key=settings.dashscope_image_api_key or settings.dashscope_api_key,
        model=settings.dashscope_image_model,
        messages=[{"role": "user", "content": [{"text": prompt}]}],
        result_format="message",
        size=settings.image_gen_size,
        watermark=False,
        prompt_extend=True,
    )

    if response.status_code != 200:
        raise RuntimeError(f"生图失败：{response.code} {response.message}")

    return response.output.choices[0].message.content[0]["image"]


async def _download_image(url: str) -> bytes:
    async with httpx.AsyncClient(timeout=IMAGE_DOWNLOAD_TIMEOUT) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        return resp.content


async def generate_image_for_question(question: Question, quiz_id: str) -> Optional[str]:
    """为单道题目生成配图并上传至 COS，返回永久 URL；任何失败都返回 None（不抛异常）。"""
    try:
        prompt = build_image_prompt(question)
        temp_url = await asyncio.to_thread(_call_image_model_sync, prompt)
        image_bytes = await _download_image(temp_url)

        settings = get_settings()
        key = f"{settings.cos_upload_prefix}{quiz_id}/{question.id}_{uuid.uuid4().hex[:8]}.png"
        return await upload_image_bytes(image_bytes, key)
    except Exception as e:
        logger.warning(
            "question_image_generation_failed",
            question_id=question.id,
            quiz_id=quiz_id,
            error=str(e),
        )
        return None


async def generate_images_for_quiz(
    questions: list[Question],
    user_id: Optional[int],
    quiz_id: str,
) -> tuple[dict[str, str], Optional[str]]:
    """为一批题目并发生成配图，返回 (question_id -> image_url 映射, 提示信息)。

    该函数不会抛出异常：任何内部错误都会被吞掉并转化为提示信息或直接忽略配图。
    """
    settings = get_settings()

    if user_id is None:
        return {}, "登录后才能使用生成图片功能，本次出题未生成配图"

    try:
        used = await image_repository.get_today_usage_count(user_id)
    except Exception as e:
        logger.warning("image_quota_check_failed", user_id=user_id, error=str(e))
        used = 0

    remaining = max(0, settings.image_gen_daily_limit - used)

    if remaining <= 0:
        return {}, f"今日生成图片次数已用完（{settings.image_gen_daily_limit} 张/天），本次出题未生成配图"

    target_questions = questions[:remaining]
    notice = None
    if len(target_questions) < len(questions):
        notice = (
            f"今日生图额度剩余 {remaining} 张，已为前 {len(target_questions)} 题生成配图，"
            "其余题目未配图"
        )

    semaphore = asyncio.Semaphore(settings.image_gen_max_concurrency)

    async def _run(q: Question) -> tuple[str, Optional[str]]:
        async with semaphore:
            url = await generate_image_for_question(q, quiz_id)
            return q.id, url

    results = await asyncio.gather(*(_run(q) for q in target_questions))

    image_map: dict[str, str] = {}
    for question_id, url in results:
        if not url:
            continue
        image_map[question_id] = url
        try:
            await image_repository.log_image_generation(user_id, quiz_id, question_id, url)
        except Exception as e:
            logger.warning("image_usage_log_failed", user_id=user_id, error=str(e))

    return image_map, notice
