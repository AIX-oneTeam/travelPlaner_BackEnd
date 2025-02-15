from app.repository.checklists.checklist_repository import save_checklist_item_repository, read_checklist_item_repository, delete_checklist_item_repository, update_checklist_item_repository
from app.dtos.checklist_models import Checklist,  PlanId
from typing import List
from sqlmodel.ext.asyncio.session import AsyncSession
import logging

logger = logging.getLogger(__name__)

#저장 서비스
async def save_checklist_service(plan_id, checklist_items: List[Checklist], session: AsyncSession):
    try:
        saved_checklist_items_num = await save_checklist_item_repository(plan_id, checklist_items, session)
        
        logger.info(f"[save_checklist service] : saved num of data -- {saved_checklist_items_num}")
        print(f"[save_checklist service] : saved num of data -- {saved_checklist_items_num}")
        return saved_checklist_items_num
    except Exception as e:
        logger.error(f"[save_checklist service] : error -- {e}")
        print(f"[save_checklist service] : error -- {e}")

#읽기 서비스 
async def read_checklist_service(plan_id : int, session:AsyncSession):
    try: 
        got_checklist = await read_checklist_item_repository(plan_id, session)
        logger.info(f"[read_checklist service] : read num of data -- {len(got_checklist)}")
        print(f"[read_checklist service] : saved num of data -- {len(got_checklist)}")
        return got_checklist  #각 item을 Checklist 모델의 인스턴스로 변환합
    except Exception as e:
        print(f"[read_checklist service] : error -- {e}")
        logger.error(f"[read_checklist service] : error -- {e}")
        return[]

    
#삭제 서비스
async def delete_checklist_service(plan_id : int, session:AsyncSession):
    try: 
        deleted_checklist_plan_id = await delete_checklist_item_repository(plan_id, session)
        
        logger.info(f"[delete_checklist_item service] : deleted plan_id -- {deleted_checklist_plan_id}")
        print(f"[delete_checklist_item service] : deleted plan_id -- {deleted_checklist_plan_id}")
        return deleted_checklist_plan_id
    
    except Exception as e :
        logger.error(f"[delete_checklist_item service] :  error -- {e}")
        print(f"[delete_checklist_item service] :  error -- {e}")

#업데이트 서비스
async def update_checklist_service(old_plan_id: int, new_plan_id: int, session: AsyncSession):
    try:
        updated_items = await update_checklist_item_repository(old_plan_id, new_plan_id, session)
        logger.info(f"[update_checklist service] : Updated checklist plan_id : {old_plan_id} -> {new_plan_id}")
        print(f"[update_checklist service] : Updated checklist plan_id : {old_plan_id} -> {new_plan_id}")
        return updated_items
    
    except Exception as e:
        logger.error(f"[update_checklist service] : error -- {e}")
        print(f"[update_checklist_item service] :  error -- {e}")
        raise
    
      