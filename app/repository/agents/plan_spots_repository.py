from sqlmodel import select, and_, desc
from app.data_models.data_model import PlanSpotMap, Plan, Spot
from sqlmodel.ext.asyncio.session import AsyncSession
import logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
"""
member_id와 plan_id로 category별 plan 조회 장소 조회
    0: 숙소 
    1: 관광지
    2: 맛집
    3: 카페
"""
async def get_member_plan_spots(plan_id: int, member_id: int, category_id:int, session: AsyncSession):
    try:
        # plan과 member_id 검증을 위한 쿼리
        plan_stmt = select(Plan).where(
            and_(Plan.id == plan_id, Plan.member_id == member_id)
        )
        result = await session.exec(plan_stmt)
        plan = result.first()

        if not plan:
            return None

        # logger.info(f"[ plan_spots_repository ] plan : {plan}")

        # plan_id와 연관된 모든 spots 조회
        spot_stmt = (
            select(PlanSpotMap, Spot)
            .join(Spot, PlanSpotMap.spot_id == Spot.id)
            .join(Plan, PlanSpotMap.plan_id == Plan.id)
            .where(
                and_(
                    PlanSpotMap.plan_id == plan_id,
                    Plan.member_id == member_id,
                    Spot.spot_category == category_id,
                )
            )
        )
        result = await session.exec(spot_stmt)
        spots = result.all()

        # logger.info(f"[ plan_spots_repository ] spots : {spots}")

        plan_spots_with_spot_info = {
            "plan": plan,
            "detail": [
                {"plan_spot": plan_spot, "spot": spot} for plan_spot, spot in spots
            ],
        }

        return (
            plan_spots_with_spot_info if plan_spots_with_spot_info is not None else None
        )
    except Exception as e:
        logger.error(f"[ plan_spots_repository ] get_plan_spots() 에러 : {e}")
        raise e


# 최근 수정된 plan 조회
async def get_latest_plan(member_id: int, session: AsyncSession):
    try:
        # member_id에 해당하는 가장 최근 plan 조회
        plan_stmt = (
            select(Plan)
            .where(Plan.member_id == member_id)
            .order_by(desc(Plan.id))
            .limit(1)
        )
        result = await session.exec(plan_stmt)
        plan = result.first()

        # logger.info(f"[ plan_spots_repository ] latest plan : {plan}")

        return plan if plan is not None else None

    except Exception as e:
        logger.error(f"[ plan_spots_repository ] get_latest_plan() 에러 : {e}")
        raise e
