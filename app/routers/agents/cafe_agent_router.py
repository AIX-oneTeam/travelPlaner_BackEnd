from typing import Optional
from fastapi import APIRouter, HTTPException, Depends
from app.services.agents.cafe_agent_service import CafeAgentService
from app.routers.agents.travel_all_schedule_agent_router import TravelPlanRequest
from app.repository.redis_client import get_redis  # Redis 연결 함수
from app.repository.db import get_async_session
from sqlalchemy.ext.asyncio import AsyncSession
from redis.asyncio import Redis
router = APIRouter()

cafe_service = CafeAgentService()

@router.post("/cafe")
async def get_cafes(
    user_input: TravelPlanRequest,
    prompt:Optional[str],
    redis_client: Redis = Depends(get_redis)
    ):
    """
    카페 정보를 가져오는 엔드포인트.
    - CrewAI 실행 후 일정(JSON) 반환.
    """
    try:
        result = await cafe_service.create_recommendation(user_input.model_dump(),
                                                          prompt = prompt,
                                                          redis_client= redis_client,
                                                        )     
        if not result:
            print("카페 결과값이 없습니다. ")

            raise HTTPException(
                status_code=404,
                detail={
                    "status": "error",
                    "message": "카페 검색 결과가 없습니다.",
                }
            )    

        return {
            "status": "success",
            "message": "카페 리스트가 생성되었습니다.",
            "data": result,
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"카페 추천 처리 중 오류가 발생했습니다: {str(e)}"
        )
        