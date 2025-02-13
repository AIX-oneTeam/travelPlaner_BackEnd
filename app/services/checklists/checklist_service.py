from app.repository.checklists.checklist_repository import save_checklist_item, read_checklist_item, delete_checklist_item
from app.dtos.checklist_models import Checklist,  PlanId
from typing import List
from sqlmodel.ext.asyncio.session import AsyncSession

#저장 서비스
async def save_checklist(checklist_items: List[Checklist], session: AsyncSession):
    try:
        saved_checklist_items = await save_checklist_item(checklist_items, session)
        return [Checklist.model_validate(item.dict()) for item in saved_checklist_items]
    except Exception as e:
        print(f"Error in save_checklist service: {e}")

#읽기 서비스 
async def read_checklist(plan_id : int, session:AsyncSession):
    try: 
        got_checklist = await read_checklist_item(plan_id, session)
        return [Checklist.model_validate(item) for item in got_checklist]  #각 item을 Checklist 모델의 인스턴스로 변환합
    except Exception as e:
        print(f"Error in read_checklis service: {e}")
        return[]


    
#삭제 서비스
async def delete_checklist(plan_id : int, session:AsyncSession):
    try: 
        deleted_checklist_item = await delete_checklist_item(plan_id, session)
        return [PlanId.model_validate(item) for item in deleted_checklist_item]
    except Exception as e :
        print(f"Error in delete_checklist service: {e}")

      