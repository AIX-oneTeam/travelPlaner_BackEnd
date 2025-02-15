from app.dtos.checklist_models import Checklist
from typing import List
from app.data_models.data_model import Checklist
from sqlmodel.ext.asyncio.session import AsyncSession
from datetime import datetime
from sqlmodel import select, delete,update
import logging
from fastapi import HTTPException
import uuid


logger = logging.getLogger(__name__)

# 저장
async def save_checklist_item_repository(plan_id:int, checklist_items: List[Checklist], session: AsyncSession)-> int :
    try:
        saved_items = []
        for item in checklist_items:
            current_time = datetime.now()
            checklist_item = Checklist(
                plan_id=plan_id,
                id=uuid.uuid4(),
                item=item.item,
                checked=item.checked,
                created_at=current_time,
                updated_at=current_time
            )
            session.add(checklist_item)
            await session.flush() 
            
            saved_item = Checklist(
                plan_id=checklist_item.plan_id,
                item=checklist_item.item,
                checked=checklist_item.checked
            )
            saved_items.append(saved_item)
        
        await session.commit()
        logger.info(f"[save_checklist_item repository] : saved num of data -- {len(saved_items)}")
        print(f"[save_checklist_item repository] : saved num of data -- {len(saved_items)}")
        return len(saved_items)
    
    except Exception as e:
        logger.error(f"[save_checklist_item repository] : error -- {e}")
        print(f"[save_checklist_item repository] : error -- {e}")
        await session.rollback()
    

# 읽기
async def read_checklist_item_repository(plan_id: int, session: AsyncSession):
    try:
        statement = select(Checklist).where(Checklist.plan_id == plan_id)
        result = await session.exec(statement)
        got_checklist = result.all()
        
        logger.info(f"[read_checklist_item repository] : read plan_id  --  {plan_id} ")
        print(f"[read_checklist_item repository] : read num of data --  {plan_id} ")
        
        return [Checklist(
            plan_id=item.plan_id,
            item=item.item,
            checked=1 if item.checked else 0  # boolean을 int로 변환
        ) for item in got_checklist]
        
    except Exception as e:
        logger.error(f"[read_checklist_item repository] : error -- {e}")
        print(f"[read_checklist_item repository] : error -- {e}")
        raise

# 삭제
async def delete_checklist_item_repository(plan_id: int, session: AsyncSession):
    try:
        statement = delete(Checklist).where(Checklist.plan_id == plan_id)
        await session.exec(statement)
        await session.commit()
        logger.info(f"[delete_checklist_item repository] : deleted plan_id -- {plan_id}")
        print(f"[delete_checklist_item repository] : deleted plan_id -- {plan_id}")
        return plan_id
    
    except Exception as e:
        logger.error(f"[delete_checklist_item repository] :  error -- {e}")
        print(f"[delete_checklist_item repository] :  error -- {e}")
        await session.rollback()
        raise

#업데이트
async def update_checklist_item_repository(old_plan_id: int, new_plan_id: int, session: AsyncSession):
    try:
        statement = update(Checklist).where(Checklist.plan_id == old_plan_id).values(plan_id=new_plan_id)
        result = await session.exec(statement)
        await session.commit()
        updated_item = result.rowcount
        logger.info(f"[update_checklist_items repository] : Updated checklist plan_id : {old_plan_id} -> {new_plan_id}")
        print(f"[update_checklist_items repository] : Updated checklist plan_id : {old_plan_id} -> {new_plan_id}")
        return updated_item
    
    except Exception as e:
        logger.error(f"[update_checklist_items repository] : error -- {e}")
        print(f"[update_checklist_items repository] : error -- {e}")
        await session.rollback()
        raise
    


