from fastapi import APIRouter, HTTPException, Depends
from app.services.checklists.checklist_service import save_checklist, read_checklist, delete_checklist
from app.dtos.checklist_models import Checklist,PlanId  # PlanId 모델은 필요 없어 보입니다. 삭제해도 됩니다.
from typing import List
from app.repository.db import get_async_session
from sqlmodel.ext.asyncio.session import AsyncSession
from app.dtos.common.response import ErrorResponse, SuccessResponse

router = APIRouter()

# 저장
@router.post("/{plan_id}", response_model=List[Checklist])
async def add_checklist(
    checklist_list: List[Checklist],
    session: AsyncSession = Depends(get_async_session),
):
    try:
        saved_checklist = await save_checklist(checklist_list, session)  # plan_id를 서비스에 전달
        print(
            f"여긴 라우터 ===================서비스 저장==========================================={checklist_list}"
        )
        return saved_checklist
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Error saving checklist: {e}"
        )

# 읽기
@router.get("/{plan_id}",response_model=List[Checklist])
async def get_checklist(plan_id:int, session: AsyncSession = Depends(get_async_session)):
    try:
        got_checklist = await read_checklist(plan_id, session)
        
        print(f'여긴 라우터 ===================플랜 아이디 ==={plan_id}==========================================={got_checklist}' )
        return got_checklist
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting checklist: {e}")
    
# 삭제
@router.delete("/{plan_id}", response_model=PlanId)
async def delete_checklist_route(plan_id:int, session: AsyncSession = Depends(get_async_session)): #함수명 변경
    try: 
        deleted_checklist =  await delete_checklist(plan_id, session)
        return PlanId(plan_Id = plan_id) #PlanId 모델에 맞게 plan_id를 넣어 리턴
    except Exception as e :
        raise HTTPException(status_code=500, detail=f"Error deleting checklist: {e}")
