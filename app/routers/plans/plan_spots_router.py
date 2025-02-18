
import logging
from fastapi import APIRouter, Depends, HTTPException, Request
from app.dtos.common.response import ErrorResponse, SuccessResponse
from app.repository.members.mebmer_repository import get_memberId_by_email
from app.services.plans.plan_spots_service import find_plan_spots
from app.repository.db import get_async_session
from sqlmodel.ext.asyncio.session import AsyncSession

router = APIRouter()


# 일정_장소 조회
@router.get("/{plan_id}")
async def read_plan_spots(plan_id: int, request: Request, session: AsyncSession = Depends(get_async_session)):
    try:
        plan_spots = await find_plan_spots(plan_id, session)
        #0. 사용자 권한 확인
        if request.state.user is not None:
            member_email = request.state.user.get("email")
            provider = request.state.user.get("provider")
            member_id = await get_memberId_by_email(email=member_email, session=session, provider=provider)

            if plan_spots["plan"]["member_id"] != member_id:
                raise HTTPException(status_code=403, detail="일정 조회 권한이 없습니다.")
        else:
            raise HTTPException(status_code=401, detail="로그인이 필요합니다.")
        
        #1. 일정_장소 조회
        logging.debug(f"💡[ plan_spots_router ] plan_spots : {plan_spots}")
        print(f"💡[ plan_spots_router ] plan_spots : {plan_spots}")

        return SuccessResponse(data=plan_spots, message="일정과 장소 정보가 성공적으로 조회되었습니다.")
    except Exception as e:
        return ErrorResponse(message="일정과 장소정보 조회에 실패했습니다.", status_code=e.status_code, error_detail=e.detail)

