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
from app.utils.time_check import time_token_check
from app.services.agents.create_dummy_data import create_dummy_data

load_dotenv()

router = APIRouter()
travel_schedule_agent_service = TravelScheduleAgentService()

logger = logging.getLogger("all_agent_router")
logger.setLevel(logging.INFO)

file_handler = logging.FileHandler('logs/all_agent.log', encoding="utf-8")
file_handler.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
file_handler.setFormatter(formatter)
logger.addHandler(file_handler)

# 에러 전용 로그 파일 생성
file_handler_error = logging.FileHandler('logs/all_agent_error.log', encoding="utf-8")
file_handler_error.setLevel(logging.ERROR)
formatter_error = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
file_handler_error.setFormatter(formatter_error)
logger.addHandler(file_handler_error)


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
    session: AsyncSession = Depends(get_async_session),
    redis_client: Redis = Depends(get_redis),
):
    try:
        # <-------dummies 테스트 시에만 활성화, 서비스 코드는 주석처리 필요--->
        # DUMMY_DATA =create_dummy_data()
        # # logger.info(f"프론트에서 받은 데이터: {user_input}")
        # # Pydantic 모델을 Python dict로 변환
        # input_dict = user_input.model_dump()
        # input_dict["member_id"] = await get_member_id_by_request(request, session)
        # input_dict["provider"] = request.state.user.get("provider")
        # input_dict["email"] = request.state.user.get("email")
        # input_dict["external_data"] = DUMMY_DATA
        
        # <--------서비스 코드(더미 테스트시 주석 처리)---->
        logger.info(f"프론트에서 받은 데이터: {user_input}")
        # Pydantic 모델을 Python dict로 변환
        input_dict = user_input.model_dump()      
        
        # 기본으로 실행할 에이전트 리스트 설정
        agent_type = ["accommodation, cafe, restaurant, site"]
        input_dict["agent_type"] = agent_type
        input_dict["member_id"] = await get_member_id_by_request(request, session)
        input_dict["provider"] = request.state.user.get("provider")
        input_dict["email"] = request.state.user.get("email")
        logger.info(f"input_dict: {input_dict}")


        # 비동기 작업 딕셔너리 생성
        tasks = {}

        if "restaurant" in agent_type:
            restaurant_service = RestaurantAgentService()
            tasks["restaurant"] = restaurant_service.create_recommendation_restaurant(input_data=input_dict, session=session, redis_client=redis_client)
            logger.info(f"restaurant Agent 결과: {tasks['restaurant']}")
            
        if "site" in agent_type:
            site_agent_service = TouristAgentService()
            tasks["site"] = site_agent_service.create_tourist_plan(input_data=input_dict, session=session, redis_client=redis_client)
            logger.info(f"Site Agent 결과: {tasks['site']}")
            
        if "cafe" in agent_type:
            cafe_agent_service = CafeAgentService()
            tasks["cafe"] = cafe_agent_service.create_recommendation_cafe(input_data=input_dict, session=session, redis_client=redis_client)
            logger.info(f"cafe Agent 결과: {tasks['cafe']}")
            

        if "accommodation" in agent_type:
            accommodation_agent_service = AccommodationAgentService()
            tasks["accommodation"] = accommodation_agent_service.create_recommendation_accommodation(input_dict)
            logger.info(f"accommodation Agent 결과: {tasks['accommodation']}")

        # 비동기 작업 병렬 실행 및 결과 매핑
        results = await asyncio.gather(*tasks.values())
        
        external_data = dict(zip(tasks.keys(), results))
        logger.info(f"external_data 결과: {external_data}")

        # 집계한 external_data를 입력 데이터에 추가
        input_dict["external_data"] = external_data
        logger.info(f"라우터받은 데이터----------------: {input_dict}")

        # <--------서비스 코드 (더미 테스트 유무 상관 없이 항상 실행)---------------------->

        # # 최종 여행 일정 생성 함수 호출 (외부 데이터 포함)
        result = await travel_schedule_agent_service.create_plan(
            input_dict, session=session, redis_client=redis_client
        )
        logger.info(f"서비스 거치고 나온 데이터----------------: {result}")

        # 푸시 메시지 전송
        await send_push_message(
            request, session, "EasyTravel 알림", "에이전트가 일을 마쳤습니다."
        )

        return {
            "status": "success",
            "message": "일정과 장소 리스트가 생성되었습니다.",
            "data": result,
        }
    except Exception as e:
        logger.error(f"Error in generate_plan: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
