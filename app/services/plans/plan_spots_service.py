
import logging
from app.utils.serialize_time import serialize_time
from app.repository.plans.plan_spots_repository import get_plan_spots
from sqlmodel.ext.asyncio.session import AsyncSession


async def find_plan_spots(plan_id: int, session: AsyncSession):
    plan_spots_with_spot_info = await get_plan_spots(plan_id, session)
    logging.debug(f"💡[ plan_spots_service ] plan_spots_with_spot_info : {plan_spots_with_spot_info}")
    print(f"💡[ plan_spots_service ] plan_spots_with_spot_info : {plan_spots_with_spot_info}")
    
    #  day_x와 order 순으로 정렬
    plan_spots_with_spot_info["detail"].sort(
        key=lambda item: (item["plan_spot"].day_x, item["plan_spot"].order)
    )

    #  Plan 데이터 직렬화
    plan_spots_with_spot_info["plan"] = serialize_time(
        plan_spots_with_spot_info["plan"], 
        ["start_date", "end_date", "created_at", "updated_at"]
    )

    # PlanSpotMap과 Spot 데이터 직렬화
    for item in plan_spots_with_spot_info["detail"]:
        item["plan_spot"] = serialize_time(
            item["plan_spot"], ["spot_time"]
        )
        item["spot"] = serialize_time(
            item["spot"], ["created_at", "updated_at"]
        )
    return plan_spots_with_spot_info
