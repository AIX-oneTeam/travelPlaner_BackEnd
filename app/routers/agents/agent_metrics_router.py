# app/routers/agent_metrics_router.py
from fastapi import APIRouter, HTTPException, Depends
from sqlmodel.ext.asyncio.session import AsyncSession
from app.repository.db import get_async_session
from app.services.agents.agent_metrics_service import get_time_distribution
import logging

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


router = APIRouter()

@router.get("/admin/metrics")
async def read_agent_metrics_distribution(
    session: AsyncSession = Depends(get_async_session)
):
    try:
        distribution = await get_time_distribution(session)
        return {"data": distribution, "message": "에이전트 실행 시간 분포 조회 성공"}
    except Exception as e:
        logger.error(f"에이전트 실행 시간 분포 조회 실패: {e}")
        raise HTTPException(status_code=500, detail=str(e))

