from datetime import time
from typing import List
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from app.repository.db import get_async_session
from app.data_models.data_model import Plan, Spot
from app.dtos.common.response import ErrorResponse, SuccessResponse
from app.repository.members.mebmer_repository import get_memberId_by_email
from app.repository.plans.plan_spots_repository import save_plan_spots
from app.repository.spots.spot_repository import delete_spot
from app.services.checklists.checklist_service import delete_checklist, save_checklist
from app.services.plans.plan_service import edit_plan, find_member_plans, find_plan, reg_plan
from app.services.plans.plan_spots_service import find_plan_spots
from app.services.spots.spot_service import reg_spot
from app.repository.plans.plan_repository import delete_plan
import logging
from sqlmodel.ext.asyncio.session import AsyncSession

logging.basicConfig()
logging.getLogger("sqlalchemy.engine").setLevel(logging.DEBUG)
logging.getLogger("sqlalchemy.pool").setLevel(logging.DEBUG)
logging.getLogger("sqlalchemy.orm").setLevel(logging.DEBUG)



router = APIRouter()

class spot_request(BaseModel):
    kor_name: str = Field(max_length=255)
    eng_name: str | None = Field(default=None, max_length=255)
    description: str = Field(max_length=255)
    address: str = Field(max_length=255)
    url: str | None = Field(default=None, max_length=2083)
    image_url: str = Field(max_length=2083)
    map_url: str = Field(max_length=2083)
    longitude: float
    latitude: float
    likes: int | None = None
    satisfaction: float | None = None
    spot_category: int

    phone_number: str | None = Field(default=None, max_length=300)
    business_status: bool | None = None
    business_hours: str | None = Field(default=None, max_length=255)

    order: int
    day_x: int
    spot_time: time | None = None

class PlanRequest(BaseModel):
    plan: Plan
    spots: list[spot_request]
    email: str

# 일정 저장
@router.post("")
async def create_plan(request_data: PlanRequest, request: Request, session: AsyncSession = Depends(get_async_session)):
    try:
        # 0. memberid 획득
        if(request.state.user is not None):
            print("request.state.user : ", request.state.user)
            member_email = request.state.user.get("email")
            member_id = await get_memberId_by_email(member_email, session)
        else:
            print("[ plan_router ] request_data.email : ", request_data.email)
            member_id = await get_memberId_by_email(request_data.email, session)
            print("[ plan_router ] member_id : ", member_id)

        # 1. 일정 저장
        plan_id = await reg_plan(request_data.plan, member_id, session)
        # 2. 장소 저장
        for spot in request_data.spots:
            spot_id = await reg_spot(Spot(**spot.model_dump(exclude={"order", "day_x", "spot_time"})), session)
            # 3. 일정-장소 매핑 저장
            await save_plan_spots(plan_id, spot_id, spot.order, spot.day_x, spot.spot_time, session)


        return SuccessResponse(data={"plan_id": plan_id}, message="일정이 성공적으로 등록되었습니다.")
    except Exception as e:
        return ErrorResponse(message="일정 등록에 실패했습니다.", error_detail=e)

# 일정 조회
# 회원의 모든 일정만 리스트 조회
@router.get("")
async def read_member_plans(request: Request, session: AsyncSession = Depends(get_async_session)):
    try:
        if(request.state.user is not None):
            member_email = request.state.user.get("email")
            member_id = await get_memberId_by_email(member_email, session)
            print("💡[ plan_router ] member_id : ", member_id)
        else:
            return ErrorResponse(message="로그인이 필요합니다.")
        plans = await find_member_plans(member_id, session)
        print("💡[ plan_router ] plans : ", plans)
        return SuccessResponse(data=plans, message="멤버의 일정 정보가 성공적으로 조회되었습니다.")
    except Exception as e:
        return ErrorResponse(message="멤버의 일정정보 조회에 실패했습니다.", error_detail=e)

# 일정 수정
@router.post("/{plan_id}")
async def update_plan(plan_id: int, request_data: PlanRequest, request: Request, session: AsyncSession = Depends(get_async_session)):
    try:
        if(request.state.user is not None):
            member_email = request.state.user.get("email")
            member_id = await get_memberId_by_email(member_email, session)
        # local 테스트용
        elif(request_data.email is not None):
            member_id = await get_memberId_by_email(request_data.email, session)
        else:
            return ErrorResponse(message="로그인이 필요합니다.")
        

        # 1. 소유자 확인
        plan = await find_plan(plan_id, session)
        if(plan.member_id != member_id):
            return ErrorResponse(message="일정 수정 권한이 없습니다.")
        
        #1. 장소 삭제
        plan_spots = await find_plan_spots(plan_id, session)
        print("💡[ plan_router ] plan_spots : ", plan_spots)
        for spot in plan_spots["detail"]:
            print("💡[ plan_router ] spot : ", spot)
            await delete_spot(spot["spot"]["id"], session)

        # 2. 일정 삭제
        await delete_plan(plan_id, session)

        # 3. 체크리스트 삭제
        await delete_checklist(plan_id, session)

        # 4. 새로운 일정 등록
        plan_id = await reg_plan(request_data.plan, member_id, session)
        for spot in request_data.spots:
            spot_id = await reg_spot(Spot(**spot.model_dump(exclude={"order", "day_x", "spot_time"})), session)
            # 3. 일정-장소 매핑 저장
            await save_plan_spots(plan_id, spot_id, spot.order, spot.day_x, spot.spot_time, session)
        
        # 5. 체크리스트 등록(없다면 무시)
        if(request_data.checklist is not None):
            await save_checklist(request_data.checklist, session)
        
        return SuccessResponse(data={"plan_id": plan_id}, message="일정이 성공적으로 수정되었습니다.")
    except Exception as e:
        logging.debug(f"💡logger: 일정 수정 오류: {e}")
        return ErrorResponse(message="일정 수정에 실패했습니다.", error_detail=e)

# 일정 삭제
@router.delete("/{plan_id}")
async def erase_plan(plan_id: int, request: Request, session: AsyncSession = Depends(get_async_session)):
    try:
        if(request.state.user is not None):
            member_email = request.state.user.get("email")
            member_id = await get_memberId_by_email(member_email, session)
        else:
            return ErrorResponse(message="로그인이 필요합니다.")
        
        # 1. 소유자 확인
        plan = await find_plan(plan_id, session)
        if(plan.member_id != member_id):
            return ErrorResponse(message="일정 삭제 권한이 없습니다.")
        
        #1. 장소 삭제
        plan_spots = await find_plan_spots(plan_id, session)
        print("💡[ plan_router ] plan_spots : ", plan_spots)
        for spot in plan_spots["detail"]:
            print("💡[ plan_router ] spot : ", spot)
            await delete_spot(spot["spot"]["id"], session)

        # 2. 일정 삭제
        await delete_plan(plan_id, session)

        # 3. 체크리스트 삭제
        await delete_checklist(plan_id, session)

        return SuccessResponse(message="일정이 성공적으로 삭제되었습니다.")
    except Exception as e:
        logging.debug(f"💡logger: 일정 삭제 오류: {e}")
        return ErrorResponse(message="일정 삭제에 실패했습니다.", error_detail=e)


