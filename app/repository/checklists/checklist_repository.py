from app.dtos.checklist_models import ChecklistCreate, ChecklistResponse
from typing import List
from fastapi import HTTPException
from app.data_models.data_model import Checklist
from sqlmodel.ext.asyncio.session import AsyncSession

# 저장
async def save_checklist_item(checklist_items: List[ChecklistCreate], session: AsyncSession) :
    try:
        saved_items = []
        for item in checklist_items:
            checklist_item = Checklist(plan_id=item.plan_id, text=item.text, checked=item.checked)
            await session.add(checklist_item)
            await session.commit()
            await session.refresh(checklist_item)
            saved_items.append(checklist_item)
        return saved_items
    except Exception as e:
        print(f"Error in save_checklist_item repository: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")



#읽기
async def read_checklist_item(plan_id: int, session: AsyncSession):
    try:
        result = await session.exec(Checklist)
        got_checklist = result.filter(Checklist.plan_id == plan_id).all()
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


    
    

