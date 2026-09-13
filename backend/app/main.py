"""FastAPI 应用入口"""

from contextlib import asynccontextmanager
import asyncio

import structlog
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.v1.routes import health, knowledge, quiz, report, user, tasks
from app.core.config import get_settings
from app.core.db import close_mysql_pool, connect_mysql
from app.core.upload_limits import UploadLimitsMiddleware
from app.core.exceptions import (
    AuthenticationError,
    ContentFilterError,
    KnowledgeBaseError,
    QuizGenerationError,
    ReportGenerationError,
)
from app.models.common import ApiResponse

logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    logger.info("app_starting", host=settings.app_host, port=settings.app_port)
    await connect_mysql()
    worker = None
    if settings.worker_enabled:
        from app.worker import run
        from app.services.job_handlers import handlers, maintenance
        worker = asyncio.create_task(run(handlers(), maintenance=maintenance))
    try:
        yield
    finally:
        if worker:
            worker.cancel()
            await asyncio.gather(worker, return_exceptions=True)
        await close_mysql_pool()
        logger.info("app_shutting_down")



app = FastAPI(
    title="LuxUmbra AI 闯关学习",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册路由
app.add_middleware(UploadLimitsMiddleware)
app.include_router(health.router, prefix="/api/v1")
app.include_router(quiz.router, prefix="/api/v1")
app.include_router(report.router, prefix="/api/v1")
app.include_router(user.router, prefix="/api/v1")
app.include_router(knowledge.router, prefix="/api/v1")
app.include_router(tasks.router, prefix='/api/v1')


# 全局异常处理
@app.exception_handler(AuthenticationError)
async def auth_error_handler(request: Request, exc: AuthenticationError):
    return JSONResponse(
        status_code=401,
        content=ApiResponse.error(code=4010, message=str(exc)).model_dump(),
    )


@app.exception_handler(ContentFilterError)
async def content_filter_handler(request: Request, exc: ContentFilterError):
    return JSONResponse(
        status_code=400,
        content=ApiResponse.error(code=4000, message=str(exc)).model_dump(),
    )


@app.exception_handler(QuizGenerationError)
async def quiz_error_handler(request: Request, exc: QuizGenerationError):
    return JSONResponse(
        status_code=500,
        content=ApiResponse.error(code=5001, message=str(exc)).model_dump(),
    )


@app.exception_handler(ReportGenerationError)
async def report_error_handler(request: Request, exc: ReportGenerationError):
    return JSONResponse(
        status_code=500,
        content=ApiResponse.error(code=5002, message=str(exc)).model_dump(),
    )


@app.exception_handler(KnowledgeBaseError)
async def knowledge_base_error_handler(request: Request, exc: KnowledgeBaseError):
    return JSONResponse(
        status_code=400,
        content=ApiResponse.error(code=4001, message=str(exc)).model_dump(),
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    """兜底异常处理：避免直接暴露裸的 "Internal Server Error"，并记录完整堆栈便于排查。"""
    logger.error(
        "unhandled_exception",
        path=request.url.path,
        method=request.method,
        error=str(exc),
        exc_info=True,
    )
    return JSONResponse(
        status_code=500,
        content=ApiResponse.error(code=5000, message="服务器内部错误，请稍后重试").model_dump(),
    )


if __name__ == "__main__":
    import uvicorn

    settings = get_settings()
    uvicorn.run(
        "app.main:app",
        host=settings.app_host,
        port=settings.app_port,
        reload=settings.app_debug,
    )
