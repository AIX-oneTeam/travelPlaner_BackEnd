
import logging
from fastapi import APIRouter, Depends, Request
from app.dtos.common.response import ErrorResponse, SuccessResponse
from app.services.plans.plan_spots_service import find_plan_spots
from app.repository.db import get_async_session
from sqlmodel.ext.asyncio.session import AsyncSession

router = APIRouter()


# 일정_장소 조회
@router.get("/{plan_id}")
async def read_plan_spots(plan_id: int, request: Request, session: AsyncSession = Depends(get_async_session)):
    try:
        # #0. 사용자 권한 확인
        # if(request.state.user is not None):
        #     member_email = request.state.user.get("email")
        #     logging.debug(f"💡[ plan_spots_router ] member_email : {member_email}")
        # else:
        #     return ErrorResponse(message="로그인이 필요합니다.")
        
        #1. 일정_장소 조회
        plan_spots = await find_plan_spots(plan_id, session)
        logging.debug(f"💡[ plan_spots_router ] plan_spots : {plan_spots}")
        print(f"💡[ plan_spots_router ] plan_spots : {plan_spots}")

        return SuccessResponse(data=plan_spots, message="일정과 장소 정보가 성공적으로 조회되었습니다.")
    except Exception as e:
        return ErrorResponse(message="일정과 장소정보 조회에 실패했습니다.", error_detail=e)

