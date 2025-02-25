# app/services/agent_metrics_service.py
from sqlmodel.ext.asyncio.session import AsyncSession
from app.repository.agents.agent_metrics_repository import get_time_distribution
import logging

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

async def get_agent_metrics_distribution(session: AsyncSession):
    """
    전체 에이전트의 실행 시간 분포를 반환하는 서비스 함수.
    
    기준:
      - under_2: 2분 이내 (<= 120초)
      - under_3: 2분 초과 ~ 3분 이하 (120초 초과 ~ 180초 이하)
      - under_4: 3분 초과 ~ 4분 이하 (180초 초과 ~ 240초 이하)
      - under_5: 4분 초과 ~ 5분 이하 (240초 초과 ~ 300초 이하)
      - over_5: 5분 초과 (300초 초과)
    """
    try:
        distribution = await get_time_distribution(session)
        return distribution
    except Exception as e:
        logger.error(f"에이전트 실행 시간 분포 서비스 에러: {e}")
        raise e


