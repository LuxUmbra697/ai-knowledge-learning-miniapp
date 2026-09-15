"""报告路由"""


from fastapi import APIRouter, Depends, Header

from app.core.auth import get_current_user
from app.models.common import ApiResponse
from app.models.report import ReportGenerateRequest
from app.services.report_service import handle_report_generate, create_report_task

router = APIRouter(prefix="/report", tags=["report"])


@router.post("/generate", response_model=ApiResponse)
async def report_generate(
    req: ReportGenerateRequest,
    user_id: int = Depends(get_current_user),
    idempotency_key: str | None = Header(default=None, alias='Idempotency-Key'),
):
    result = await handle_report_generate(req, user_id=user_id, key=idempotency_key)
    return ApiResponse.success(data=result.model_dump())


@router.post('/generate/async', response_model=ApiResponse)
async def report_generate_async(req: ReportGenerateRequest, user_id: int = Depends(get_current_user),
                                idempotency_key: str | None = Header(default=None, alias='Idempotency-Key')):
    return ApiResponse.success(data=await create_report_task(req, user_id, idempotency_key))
