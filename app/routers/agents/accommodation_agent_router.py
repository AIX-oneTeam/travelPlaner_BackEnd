from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, HTTPException
from app.services.agents.accommodation_agent_service2 import AccommodationAgentService

router = APIRouter()

class Companion(BaseModel):
    label: str
    count: int

class TravelPlanRequest(BaseModel):
    ages: str
    companion_count: List[Companion]
    start_date: str
    end_date: str
    concepts: List[str]
    main_location: str
    prompt: Optional[str] = None


@router.post("/accommodation")
async def get_accommodation(user_input: TravelPlanRequest ):
    """숙소 추천 엔드포인트"""
    
    print("프런트에서 데이터 받음")
    
    try:
        # model_dump()를 사용하여 입력 데이터를 dict 형태로 변환
        input_data = user_input.model_dump()
        try:
            result = await AccommodationAgentService.create_recommendation(input_data)
        except Exception as e:
            print(f"[ERROR] accommodationagentservie create_recommendation() 오류 발생: {e}")
            raise HTTPException(status_code=500, detail="추천 생성 중 오류 발생")

        print("accommodation_response:", result)

        return {
            "status": "success",
            "message": "숙소 리스트가 생성되었습니다.",
            "data": result,
        }

    except Exception as e:
        print(f"[ERROR] 숙소 추천 요청 처리 중 오류 발생: {e}")
        raise HTTPException(status_code=500, detail=str(e))
