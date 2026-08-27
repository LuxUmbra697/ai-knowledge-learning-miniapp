"""报告路由"""

from typing import Optional

from fastapi import APIRouter, Depends

from app.core.auth import get_optional_user
from app.models.common import ApiResponse
from app.models.report import ReportGenerateRequest
from app.services.report_service import handle_report_generate

router = APIRouter(prefix="/report", tags=["report"])


@router.post("/generate", response_model=ApiResponse)
async def report_generate(
    req: ReportGenerateRequest,
    user_id: Optional[int] = Depends(get_optional_user),
):
    result = await handle_report_generate(req, user_id=user_id)
    return ApiResponse.success(data=result.model_dump())
