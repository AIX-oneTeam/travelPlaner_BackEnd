from fastapi import APIRouter, HTTPException, Query, Body, Depends
from app.repository.db import get_async_session
from app.repository.redis_client import get_redis
from sqlmodel.ext.asyncio.session import AsyncSession
from typing import Optional
from app.routers.agents.travel_all_schedule_agent_router import TravelPlanRequest
from app.services.agents.restaurant_agent_service import RestaurantAgentService
from redis.asyncio import Redis
import logging

logger = logging.getLogger(__name__)

router = APIRouter()

restaurant_service = RestaurantAgentService()


@router.post("/restaurant")
async def get_restaurants(
    user_input: TravelPlanRequest = Body(...),
    session: AsyncSession = Depends(get_async_session),
    redis_client: Redis = Depends(get_redis),
    prompt: Optional[str] = Query(None),
):
    """
    맛집 추천 엔드포인트
    """
    try:
        # model_dump()를 사용하여 입력 데이터를 dict 형태로 변환
        input_data = user_input.model_dump()
        # print(f"input_data : {input_data}")

        if prompt:
            input_data["prompt"] = prompt

        try:
            result = await restaurant_service.create_recommendation_restaurant(
                input_data=input_data,
                session=session,
                redis_client=redis_client,
                prompt=prompt,
            )
        except Exception as e:
            logger.error(f"[ERROR] create_recommendation() 오류 발생: {e}")
            raise HTTPException(status_code=500, detail="추천 생성 중 오류 발생")

        logger.info(f"restaurant_response: {result}")

        return {
            "status": "success",
            "message": "맛집 리스트가 생성되었습니다.",
            "data": result,
        }

    except Exception as e:
        logger.error(f"[ERROR] 요청 처리 중 오류 발생: {e}")
        raise HTTPException(status_code=500, detail=str(e))
