from app.data_models.data_model import Plan
from app.repository.plans.plan_repository import get_member_plans, get_plan, save_plan
from sqlmodel.ext.asyncio.session import AsyncSession

import logging
logger = logging.getLogger(__name__)

async def reg_plan(plan: Plan, member_id: int, session: AsyncSession):
    logger.info(f"[ plan_service ] member_id : {member_id}")  # 디버깅용
    plan.member_id = member_id
    logger.info(f"[ plan_service ] plan.member_id : {plan.member_id}")  # 디버깅용
    plan_id = await save_plan(plan, session)
    return plan_id

async def edit_plan(plan_id: int, plan: Plan, member_id: int, session: AsyncSession):
    plan.member_id = member_id
    plan_id = await save_plan(plan, session, plan_id)
    return plan_id

async def find_plan(plan_id: int, session: AsyncSession):
    plan = await get_plan(plan_id, session)

    return plan

async def find_member_plans(member_id: int, session: AsyncSession):
    logger.info(f"💡[ plan_service ] find_member_plans() 호출 : {member_id}")
    plans = await get_member_plans(member_id, session)
    logger.info(f"💡[ plan_service ] find_member_plans() 결과 : {plans}")
    return plans

