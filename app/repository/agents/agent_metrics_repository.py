from app.data_models.data_model import AgentMetrics
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlmodel import text
import logging

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

async def save_execution_time(agent_name: str, execution_time: float , session: AsyncSession):
    """
    실행 시간을 저장하는 함수
    """
    try:
        new_metric = AgentMetrics(agent_name=agent_name , response_time=execution_time)
        session.add(new_metric)
        await session.commit()
        return new_metric
    except Exception as e:
        await session.rollback()
        raise e
    

async def get_time_distribution(agent_name: str, session: AsyncSession):
    """
    특정 에이전트의 실행 시간(속도)을 날짜별 및 구간별로 집계하여 반환합니다.
    
    기준:
      - under_2: 2분 이내 (<= 120초)
      - under_3: 2분 초과 ~ 3분 이하 (120초 초과 ~ 180초 이하)
      - under_4: 3분 초과 ~ 4분 이하 (180초 초과 ~ 240초 이하)
      - under_5: 4분 초과 ~ 5분 이하 (240초 초과 ~ 300초 이하)
      - over_5: 5분 이상 (300초 초과)
    """
    query = text("""
        SELECT
            DATE(created_at) AS metric_date,
            SUM(CASE WHEN response_time <= 120 THEN 1 ELSE 0 END) AS under_2,
            SUM(CASE WHEN response_time > 120 AND response_time <= 180 THEN 1 ELSE 0 END) AS under_3,
            SUM(CASE WHEN response_time > 180 AND response_time <= 240 THEN 1 ELSE 0 END) AS under_4,
            SUM(CASE WHEN response_time > 240 AND response_time <= 300 THEN 1 ELSE 0 END) AS under_5,
            SUM(CASE WHEN response_time > 300 THEN 1 ELSE 0 END) AS over_5
        FROM agent_metrics
        WHERE agent_name = :agent_name
        GROUP BY DATE(created_at)
        ORDER BY metric_date DESC
    """)
    
    result = await session.execute(query, {"agent_name": agent_name})
    rows = result.fetchall()
    
    distribution = []
    for row in rows:
        distribution.append({
            "metric_date": str(row.metric_date),  # 날짜를 문자열로 변환
            "under_2": row.under_2,
            "under_3": row.under_3,
            "under_4": row.under_4,
            "under_5": row.under_5,
            "over_5": row.over_5,
        })
    return distribution
