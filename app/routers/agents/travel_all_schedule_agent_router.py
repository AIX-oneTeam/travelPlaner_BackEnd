import logging
import os
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from typing import List, Optional
import asyncio

from redis import Redis

# 서비스 클래스 임포트
from app.repository.db import get_async_session
from app.repository.fcmToken.fcm_token_respository import get_fcm_token
from app.repository.redis_client import get_redis
from app.services.agents.travel_all_schedule_agent_service import (
    TravelScheduleAgentService,
)
from app.services.agents.site_agent_service import TouristAgentService
from app.services.agents.cafe_agent_service import CafeAgentService
from app.services.agents.restaurant_agent_service import RestaurantAgentService
from app.services.agents.accommodation_agent_service import AccommodationAgentService
from app.services.members.member_service import get_member_id_by_request
from app.services.messaging.messaging_service import send_push_message
from sqlmodel.ext.asyncio.session import AsyncSession

# 테스트용 환경변수 로드
from dotenv import load_dotenv

from app.utils.time_check import time_check
load_dotenv()

router = APIRouter()
travel_schedule_agent_service = TravelScheduleAgentService()

logger = logging.getLogger("app.utils.time_check")

class Companion(BaseModel):
    label: str
    count: int


class TravelPlanRequest(BaseModel):
    ages: str
    companion_count: List[Companion]
    start_date: str
    end_date: str
    concepts: List[str]
    main_location: str
    prompt: Optional[str] = Field(default=None)
    plan_id: Optional[int] = None
    email: Optional[str] = None


@router.post("/plan")
async def generate_plan(
    request: Request,
    user_input: TravelPlanRequest,
    agent_type: List[str] = Query(..., alias="agent_type[]"),
    session: AsyncSession = Depends(get_async_session),
    redis_client: Redis = Depends(get_redis)
):
    try:
        print("프론트에서 받은 데이터:", user_input)

        # Pydantic 모델을 Python dict로 변환 후, 에이전트 타입 추가
        input_dict = user_input.model_dump()
        logger.info(f"{input_dict['main_location']}, {input_dict['start_date']}, {input_dict['end_date']}, {input_dict['concepts']} 에 대한 여행 일정 생성 시작")
        input_dict["agent_type"] = agent_type

        # 비동기 작업 딕셔너리 생성
        tasks = {}

        # 각 외부 에이전트 호출 및 결과 집계
        if "restaurant" in agent_type:
            restaurant_service = RestaurantAgentService()
            tasks["restaurant"] = restaurant_service.create_recommendation_restaurant(
                input_dict, redis_client=redis_client
            )
        if "site" in agent_type:
            site_agent_service = TouristAgentService()
            tasks["site"] = site_agent_service.create_tourist_plan(input_dict)
        if "cafe" in agent_type:
            cafe_agent_service = CafeAgentService()
            tasks["cafe"] = cafe_agent_service.create_cafe_recommendation(input_dict, redis_client= redis_client)
        if "accommodation" in agent_type:
            accommocation_agent_service = AccommodationAgentService()
            tasks["accommodation"] = accommocation_agent_service.create_recommendation_accommodation(input_dict)

        # 비동기 작업 병렬 실행 및 결과 매핑
        results = await asyncio.gather(*tasks.values())
        external_data = dict(zip(tasks.keys(), results))

        # 집계한 external_data를 입력 데이터에 추가합니다.
        input_dict["external_data"] = external_data
        logging.info(f"라우터받은 데이터----------------: {input_dict}")
        # 최종 여행 일정 생성 함수 호출 (외부 데이터가 포함된 상태)
        result = await travel_schedule_agent_service.create_plan(input_dict)

        # 푸시 메시지 전송
        await send_push_message(request, session, "EasyTravel 알림", "에이전트가 일을 마쳤습니다.")

        return {
            "status": "success",
            "message": "일정과 장소 리스트가 생성되었습니다.",
            "data": result,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
