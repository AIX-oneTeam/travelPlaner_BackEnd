from app.repository.checklists.checklist_repository import save_checklist_item, read_checklist_item, delete_checklist_item, update_checklist_items
from app.dtos.checklist_models import Checklist,  PlanId
from typing import List
from sqlmodel.ext.asyncio.session import AsyncSession
import logging

logger = logging.getLogger(__name__)

#저장 서비스
async def save_checklist(checklist_items: List[Checklist], session: AsyncSession):
    try:
        saved_checklist_items_num = await save_checklist_item(checklist_items, session)
        
        logger.info(f"[save_checklist service] : saved num of data -- {saved_checklist_items_num}")
        print(f"[save_checklist service] : saved num of data -- {saved_checklist_items_num}")
        print(f'여긴 서비스 ===============================저장 중 ==============================={checklist_items}' )
        return saved_checklist_items_num
    except Exception as e:
        logger.error(f"[save_checklist service] : error -- {e}")
        print(f"[save_checklist service] : error -- {e}")

#읽기 서비스 
async def read_checklist(plan_id : int, session:AsyncSession):
    try: 
        got_checklist = await read_checklist_item(plan_id, session)
        
        print(f'여긴 서비스 =============================================================={got_checklist}' )
        return got_checklist  #각 item을 Checklist 모델의 인스턴스로 변환합
    except Exception as e:
        print(f"Error in read_checklis service: {e}")
        return[]

    
#삭제 서비스
async def delete_checklist(plan_id : int, session:AsyncSession):
    try: 
        deleted_checklist_item = await delete_checklist_item(plan_id, session)
        
        logger.info(f"[delete_checklist_item service] : deleted plan_id -- {deleted_checklist_item}")
        print(f"[delete_checklist_item service] : deleted plan_id -- {deleted_checklist_item}")
        return deleted_checklist_item
    
    except Exception as e :
        logger.error(f"[delete_checklist_item service] :  error -- {e}")
        print(f"[delete_checklist_item service] :  error -- {e}")
        print(f"Error in delete_checklist service: {e}")

#업데이트 서비스
async def update_checklist(old_plan_id: int, new_plan_id: int, session: AsyncSession):
    try:
        updated_items = await update_checklist_items(old_plan_id, new_plan_id, session)
        logger.info(f"[update_checklist service] : Updated {updated_items} checklist items")
        return updated_items
    except Exception as e:
        logger.error(f"[update_checklist service] : error -- {e}")
        raise
    
      