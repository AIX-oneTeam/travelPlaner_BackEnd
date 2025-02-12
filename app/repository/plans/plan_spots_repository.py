from sqlmodel import select
from app.data_models.data_model import PlanSpotMap, Plan, Spot
from sqlmodel.ext.asyncio.session import AsyncSession

async def save_plan_spots (plan_id:int, spot_id:int, order:int, day_x:str, spot_time:str, session: AsyncSession):
    try:
        await session.add(PlanSpotMap(
            plan_id=plan_id,
            spot_id=spot_id,
            order=order,
            day_x=day_x,
            spot_time=spot_time
            ))
    except Exception as e:
        print("[ planSpotRepository ] save_plan_spots() 에러 : ", e)
        raise e

async def get_plan_spots(plan_id: int, session: AsyncSession):
    try:
        plan_stmt = select(Plan).where(Plan.id == plan_id)
        result = await session.exec(plan_stmt)
        plan = result.first()

        print(f"💡[ plan_spots_repository ] plan : {plan}")

        spot_stmt = (
            select(PlanSpotMap, Spot)
            .join(Spot, PlanSpotMap.spot_id == Spot.id)  
            .where(PlanSpotMap.plan_id == plan_id)  
        )
        result = await session.exec(spot_stmt)
        spots = result.all()

        print(f"💡[ plan_spots_repository ] spots : {spots}")

        plan_spots_with_spot_info = {
            "plan": plan,
            "detail" : [
            {
                "plan_spot": plan_spot,
                "spot": spot
            }
            for plan_spot, spot in spots
        ]}

        return plan_spots_with_spot_info if plan_spots_with_spot_info is not None else None
    except Exception as e:
        print("[ plan_spots_repository ] get_plan_spots() 에러 : ", e)
        raise e

