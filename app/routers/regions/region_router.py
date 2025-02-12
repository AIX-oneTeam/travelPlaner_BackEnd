from fastapi import APIRouter, Depends
from app.dtos.common.response import ErrorResponse, SuccessResponse
from app.services.regions.region_service import (
    get_all_divisions_service,
)
from app.repository.db import get_async_session
from sqlmodel.ext.asyncio.session import AsyncSession

router = APIRouter()

# 모든 행정구역 데이터 조회
@router.get("/all")
async def fetch_all_divisions(session: AsyncSession = Depends(get_async_session)):
    try:
        divisions = await get_all_divisions_service(session)
        return SuccessResponse(
            data={"divisions": divisions},
            message="전체 지역 정보가 성공적으로 조회되었습니다.",
        )
    except Exception as e:
        return ErrorResponse(
            message="전체 지역 정보를 조회하는 데 실패했습니다.", error_detail=str(e)
        )
