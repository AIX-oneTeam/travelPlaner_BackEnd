from fastapi import APIRouter, HTTPException, Depends
from app.services.agents.site_agent_service import TouristAgentService
from app.repository.redis_client import get_redis
from app.repository.db import get_async_session
from redis.asyncio import Redis
from sqlmodel.ext.asyncio.session import AsyncSession
from app.routers.agents.travel_all_schedule_agent_router import TravelPlanRequest
import logging

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/site")
async def get_site_plan(
    plan: TravelPlanRequest,  # TravelPlanRequest를 이용해 입력 검증 수행
    redis_client: Redis = Depends(get_redis),
    session: AsyncSession = Depends(get_async_session),
):
    """
    관광지 추천 엔드포인트.
    클라이언트는 JSON 데이터를 본문에 전송합니다.
    """
    try:

        if not isinstance(plan.companion_count, list):
            plan.companion_count = []

        plan_data = plan.dict(exclude_unset=True)

        if "member_id" not in plan_data:
            plan_data["member_id"] = 1
        site_service = TouristAgentService()
        result = await site_service.create_tourist_plan(
            plan_data, redis_client=redis_client, session=session
        )

        return {
            "status": "success",
            "message": "관광지 추천 결과가 생성되었습니다.",
            "data": result,
        }
    except Exception as e:
        logger.error("오류 발생: %s", e)
        raise HTTPException(status_code=500, detail=str(e))
