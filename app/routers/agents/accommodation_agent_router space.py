from pydantic import BaseModel
from typing import List, Dict, Any
from fastapi import APIRouter, HTTPException
import asyncio
from app.services.agents.accommodation_agent_4 import run
import json

router = APIRouter()

class UserInputData(BaseModel):
    location: str
    check_in_date: str
    check_out_date: str
    age_group: int
    adults: int
    children: int
    keyword: List[str]
    prompt : str  = None   #프롬프트는 수정에서만 사용
  

@router.post("/accommodations")
async def get_accommodations(user_input: UserInputData):
    """
    숙소 추천 API
    """
    try:
        crew_output = await asyncio.to_thread(
            run,
            location=user_input.location,
            check_in_date=user_input.check_in_date,
            check_out_date=user_input.check_out_date,
            age_group=user_input.age_group,
            adults=user_input.adults,
            children=user_input.children,
            keyword=user_input.keyword,
            prompt =user_input.prompt
        )

        # json 문자열을 객체로 변환
        parsed_output = json.loads(crew_output)
        
        
        return {"result": parsed_output}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"[숙소 추천 API] 에러: {str(e)}")
