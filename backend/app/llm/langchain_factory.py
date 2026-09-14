"""LangChain ChatOpenAI 工厂"""

from functools import lru_cache

from langchain_openai import ChatOpenAI

from app.core.config import get_settings


@lru_cache()
def get_chat_model(temperature: float = 0.4) -> ChatOpenAI:
    settings = get_settings()
    if not settings.deepseek_api_key:
        raise ValueError('DEEPSEEK_API_KEY is not configured')
    return ChatOpenAI(
        model=settings.deepseek_model,
        base_url=settings.deepseek_base_url,
        api_key=settings.deepseek_api_key,
        temperature=temperature,
        max_tokens=4096,
        max_retries=0,
        timeout=20,
    )
