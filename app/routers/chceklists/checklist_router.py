from fastapi import APIRouter, HTTPException, Depends
from app.services.checklists.checklist_service import save_checklist_service, read_checklist_service, delete_checklist_service
from app.dtos.checklist_models import Checklist,PlanId  
from typing import List
from app.repository.db import get_async_session
from sqlmodel.ext.asyncio.session import AsyncSession
import logging

logger = logging.getLogger(__name__)
router = APIRouter()

# 저장 및 삭제
@router.post("/{plan_id}")
async def add_checklist_router(
    plan_id : int,
    checklist_list: List[Checklist],
    session: AsyncSession = Depends(get_async_session),
):
    try:
        await delete_checklist_service(plan_id, session)
        
        saved_checklist_num = await save_checklist_service(plan_id, checklist_list, session)   
        logger.info(f"[add_checklist_router] : plan_id -- {plan_id}, saved num of data -- {saved_checklist_num}")
        print(f"[add_checklist_router] : plan_id -- {plan_id}, saved num of data -- {saved_checklist_num}")
        return [saved_checklist_num]
    
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Error saving checklist: {e}"
        )

# 읽기
@router.get("/{plan_id}",response_model=List[Checklist])
async def get_checklist_router(plan_id:int, session: AsyncSession = Depends(get_async_session)):
    try:
        get_checklist = await read_checklist_service(plan_id, session)
        
        logger.info(f"[get_checklist_router] : saved num of data -- {get_checklist}")
        print(f"[get_checklist_router] : saved num of data -- {get_checklist}")
        return get_checklist
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting checklist: {e}")
    
# 삭제
@router.delete("/{plan_id}", response_model=PlanId)
async def delete_checklist_router(plan_id:int, session: AsyncSession = Depends(get_async_session)): 
    try: 
        deleted_checklist =  await delete_checklist_service(plan_id, session)
        
        logger.info(f"[delete_checklist_router] : deleted plan_id -- {deleted_checklist}")
        print(f"[delete_checklist_router] : deleted plan_id -- {deleted_checklist}")
        return PlanId(plan_Id = deleted_checklist) #PlanId 모델에 맞게 plan_id를 넣어 리턴
    
    except Exception as e :
        logger.info(f"[delete_checklist_router] : error -- {e}")
        print(f"[delete_checklist_router] : error -- {e}")
        raise HTTPException(status_code=500, detail=f"Error deleting checklist: {e}")
