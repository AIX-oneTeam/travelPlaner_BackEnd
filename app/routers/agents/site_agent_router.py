from fastapi import APIRouter, HTTPException, Request, Depends
import traceback
from app.services.agents.site_agent_service import TouristAgentService
from app.repository.redis_client import get_redis
from app.repository.db import get_async_session
from redis.asyncio import Redis
from sqlmodel.ext.asyncio.session import AsyncSession
import logging

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/site")
async def get_site_plan(
    request: Request,
    redis_client: Redis = Depends(get_redis),
    session: AsyncSession = Depends(get_async_session),
):
    """
    관광지 에이전트를 이용한 추천 엔드포인트.
    클라이언트는 URL 쿼리 파라미터나 본문에 JSON 데이터를 전송합니다.
    """
    try:
        plan_data = await request.json()

        if not isinstance(plan_data.get("companion_count", []), list):
            plan_data["companion_count"] = []

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
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))
