from app.dtos.checklist_models import Checklist
from typing import List
from fastapi import HTTPException
from app.data_models.data_model import Checklist
from sqlmodel.ext.asyncio.session import AsyncSession
from datetime import datetime
from sqlmodel import select

# 저장
async def save_checklist_item(checklist_items: List[Checklist], session: AsyncSession) :
    try:
        saved_items = []
        for item in checklist_items:
            current_time = datetime.now
            checklist_item = Checklist(
                plan_id=item.plan_id,
                item=item.text,
                checked=item.checked,
                created_at=current_time,
                updated_at=current_time
            )
            session.add(checklist_item)
            
            # ChecklistCreate 객체로 변환하여 저장 (created_at과 updated_at 제외)
            saved_item = Checklist(
                plan_id=checklist_item.plan_id,
                text=checklist_item.item,
                checked=checklist_item.checked
            )
            saved_items.append(saved_item)
        
        await session.commit()
        
        return saved_items
    except Exception as e:
        print(f"Error in save_checklist_item repository: {e}")
        await session.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")



#읽기
async def read_checklist_item(plan_id: int, session: AsyncSession):
    try:
        statement = select(Checklist).where(Checklist.plan_id == plan_id)
        result = await session.exec(statement)
        got_checklist = result.all()
        return got_checklist
    except Exception as e:
        print(f"Error in read_checklist_item repository: {e}")
        raise HTTPException(status_code=500, detail="데이터베이스 조회 중 오류가 발생했습니다.")


#삭제
async def delete_checklist_item(plan_id : int, session: AsyncSession):
    try:
        result = await session.exec(Checklist)
        result.filter(Checklist.plan_id == plan_id).delete()
        return plan_id
    except Exception as e:
        print(f"Error int delete_checklist_item repository: {e}")


    
    

