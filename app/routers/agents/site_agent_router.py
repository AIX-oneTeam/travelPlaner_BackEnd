import traceback
from fastapi import APIRouter, HTTPException, Depends
from app.services.agents.site_agent_service import TouristAgentService
from app.repository.redis_client import get_redis
from app.repository.db import get_async_session
from redis.asyncio import Redis
from sqlmodel.ext.asyncio.session import AsyncSession
import logging
from app.repository.members.mebmer_repository import get_memberId_by_email
from app.routers.agents.travel_all_schedule_agent_router import TravelPlanRequest

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/site")
async def get_site_plan(
    plan: TravelPlanRequest,  # TravelPlanRequest를 이용해 입력 검증 수행
    redis_client: Redis = Depends(get_redis),
    session: AsyncSession = Depends(get_async_session),
):
    """
    관광지 에이전트를 이용한 추천 엔드포인트.
    (이제 반환 데이터에는 spot_time 항목이 없습니다.)
    클라이언트는 JSON 데이터를 본문에 전송합니다.
    """
    try:
        # companion_count가 리스트가 아닌 경우 빈 리스트로 초기화
        if not isinstance(plan.companion_count, list):
            plan.companion_count = []

        # 테스트용으로 하드코딩된 인증 로직 (실제 환경에서는 OAuth나 JWT를 이용)
        auth_header = plan.dict().get("headers", {}).get("Authorization")
        if not auth_header:
            auth_header = "Bearer your_token_here"
        if not auth_header:
            raise HTTPException(status_code=401, detail="Authentication required")

        # 테스트용 하드코딩된 이메일 (실제 환경에서는 토큰에서 추출)
        email = "119drogba@gmail.com"
        provider = "google"

        # 이메일로 member_id 조회
        member_id = await get_memberId_by_email(email, session, provider)
        if not member_id:
            raise HTTPException(status_code=401, detail="사용자를 찾을 수 없습니다.")

        # plan 데이터에 member_id 추가
        plan_data = plan.dict(exclude_unset=True)
        plan_data["member_id"] = member_id

        site_service = TouristAgentService()
        result = await site_service.create_tourist_plan(
            plan_data, redis_client=redis_client, session=session
        )

        return {
            "status": "success",
            "message": "관광지 추천 결과가 생성되었습니다.",
            "data": {"spots": result},
        }
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))
