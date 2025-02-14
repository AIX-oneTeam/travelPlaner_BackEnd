from app.dtos.checklist_models import Checklist
from typing import List
from app.data_models.data_model import Checklist
from sqlmodel.ext.asyncio.session import AsyncSession
from datetime import datetime
from sqlmodel import select, delete
import logging
from fastapi import HTTPException
import uuid


logger = logging.getLogger(__name__)

# 저장
# 저장
async def save_checklist_item(checklist_items: List[Checklist], session: AsyncSession) :
    try:
        saved_items = []
        for item in checklist_items:
            current_time = datetime.now
            
            checklist_item = Checklist(
                plan_id=item.plan_id,
                id=uuid.uuid4(),
                item=item.item,
                checked=item.checked,
                created_at=current_time,
                updated_at=current_time
            )
            session.add(checklist_item)
            await session.flush() 
            
            # ChecklistCreate 객체로 변환하여 저장 (created_at과 updated_at 제외)
            saved_item = Checklist(
                plan_id=checklist_item.plan_id,
                item=checklist_item.item,
                checked=checklist_item.checked
            )
            saved_items.append(saved_item)
        
        await session.commit()
        print(f'여긴 리파지토리 입력 데이터:============================================================== {checklist_items}')
        print(f'여긴 리파지토리 저장된 아이템:============================================================== {saved_item}')
        return saved_items
    except Exception as e:
        print(f"Error in save_checklist_item repository: {e}")
        await session.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")
# 읽기
async def read_checklist_item(plan_id: int, session: AsyncSession):
    try:
        statement = select(Checklist).where(Checklist.plan_id == plan_id)
        result = await session.exec(statement)
        got_checklist = result.all()
        
        logger.info(f"Retrieved {len(got_checklist)} checklist items for plan_id: {plan_id}")
        
        return [Checklist(
            plan_id=item.plan_id,
            item=item.item,
            checked=1 if item.checked else 0  # boolean을 int로 변환
        ) for item in got_checklist]
    except Exception as e:
        logger.error(f"Error in read_checklist_item repository: {e}")
        raise

# 삭제
async def delete_checklist_item(plan_id: int, session: AsyncSession):
    try:
        statement = delete(Checklist).where(Checklist.plan_id == plan_id)
        result = await session.exec(statement)
        await session.commit()
        logger.info(f"Deleted checklist items for plan_id: {plan_id}")
        return result
    except Exception as e:
        logger.error(f"Error in delete_checklist_item repository: {e}")
        await session.rollback()
        raise
