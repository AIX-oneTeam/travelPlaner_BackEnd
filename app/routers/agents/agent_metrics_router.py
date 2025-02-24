# app/routers/agent_metrics_router.py
from fastapi import APIRouter, HTTPException, Depends
from sqlmodel.ext.asyncio.session import AsyncSession
from app.repository.db import get_async_session
from app.services.agents.agent_metrics_service import get_agent_metrics_distribution
import logging

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


router = APIRouter()

@router.get("/metrics")
async def read_agent_metrics_distribution(
    agent_name: str, 
    session: AsyncSession = Depends(get_async_session)
):
    """
    특정 에이전트의 실행 시간 분포를 조회합니다.
    
    기준:
      - under_2: 2분 이내 (<= 120초)
      - under_3: 2분 초과 ~ 3분 이하 (120초 초과 ~ 180초 이하)
      - under_4: 3분 초과 ~ 4분 이하 (180초 초과 ~ 240초 이하)
      - under_5: 4분 초과 ~ 5분 이하 (240초 초과 ~ 300초 이하)
      - over_5: 5분 초과 (300초 초과)
    """
    try:
        distribution = await get_agent_metrics_distribution(agent_name, session)
        return {"data": distribution, "message": "에이전트 실행 시간 분포 조회 성공"}
    except Exception as e:
        logger.error(f"에이전트 실행 시간 분포 조회 실패: {e}")
        raise HTTPException(status_code=500, detail=str(e))
