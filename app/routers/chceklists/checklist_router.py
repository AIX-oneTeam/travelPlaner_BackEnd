from fastapi import APIRouter, HTTPException, Depends
from app.services.checklists.checklist_service import save_checklist, read_checklist, delete_checklist
from app.dtos.checklist_models import ChecklistListCreate, ChecklistResponse,PlanId, ChecklistCreate
from typing import List
from app.repository.db import get_async_session
from sqlmodel.ext.asyncio.session import AsyncSession

router = APIRouter()

#저장
@router.post("", response_model=List[ChecklistResponse])
async def add_checklist(checklist_list: ChecklistListCreate, session: AsyncSession = Depends(get_async_session)):
    try:
        saved_checklist = await save_checklist(checklist_list, session)
        return saved_checklist
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error saving checklist: {e}")

#읽기    
@router.get("/{plan_id}",response_model=List[ChecklistResponse])
async def get_checklist(plan_id:int, session: AsyncSession = Depends(get_async_session)):
    try:
        got_checklist = await read_checklist(plan_id, session)
        return got_checklist
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting checklist: {e}")
    
#삭제
@router.delete("/{plan_id}", response_model=PlanId)
async def delete_checklist(plan_id:int, session: AsyncSession = Depends(get_async_session)):
    try: 
        deleted_checklist =  await delete_checklist(plan_id, session)
        return deleted_checklist
    except Exception as e :
        raise HTTPException(status_code=500, detail=f"Error deleting checklist: {e}")

        
    

