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
    

async def get_time_distribution(session: AsyncSession):
    query = text("""
        SELECT
            agent_name,
            DATE(created_at) AS metric_date,
            SUM(CASE WHEN response_time <= 120 THEN 1 ELSE 0 END) AS under_2,
            SUM(CASE WHEN response_time > 120 AND response_time <= 180 THEN 1 ELSE 0 END) AS under_3,
            SUM(CASE WHEN response_time > 180 AND response_time <= 240 THEN 1 ELSE 0 END) AS under_4,
            SUM(CASE WHEN response_time > 240 AND response_time <= 300 THEN 1 ELSE 0 END) AS under_5,
            SUM(CASE WHEN response_time > 300 THEN 1 ELSE 0 END) AS over_5
        FROM agent_metrics
        GROUP BY agent_name, DATE(created_at)
        ORDER BY agent_name, metric_date DESC
    """)
    
    result = await session.execute(query)
    rows = result.fetchall()
    
    distribution = []
    for row in rows:
        distribution.append({
            "agent_name": row.agent_name,
            "metric_date": str(row.metric_date),
            "under_2": row.under_2,
            "under_3": row.under_3,
            "under_4": row.under_4,
            "under_5": row.under_5,
            "over_5": row.over_5,
        })
    return distribution
