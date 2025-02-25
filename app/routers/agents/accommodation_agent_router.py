import logging
import time
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, HTTPException
from app.services.agents.accommodation_agent_service import AccommodationAgentService

router = APIRouter()

logger = logging.getLogger(__name__)

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

class AccommodationResponse(BaseModel):
    status: str
    message: str
    data: Dict[str, Any]


@router.post("/accommodation", response_model=AccommodationResponse)
async def get_accommodation(user_input: TravelPlanRequest, prompt: Optional[str] = None):
    """숙소 추천 엔드포인트"""
    
    start_time = time.time()
    
    try:
        input_data = user_input.model_dump()
        logger.info(f"prompt")
        if prompt:
            input_data['prompt'] = prompt   
            logger.info(f"사용자 입력값 -- {user_input}")      
        try:
            accommodation_service = AccommodationAgentService() 
            result = await accommodation_service.create_recommendation_accommodation(user_input=input_data)
        except Exception as e:
            logger.error(f"[ERROR] accommodationagentservie create_accommodation_recemmendation() 오류 발생: {e}")
            raise HTTPException(status_code=500, detail="추천 생성 중 오류 발생")

        end_time = time.time()
        execution_time = end_time - start_time

        logger.info("accommodation_response:", result)
        print(f"---------출력값 확인 -----  {result}")
        print(f"---------출력 시간  확인 -----  {execution_time}")

        return AccommodationResponse(
            status="success",
            message="숙소 리스트가 생성되었습니다.",
            data=result,
        )

    except Exception as e:
        logger.error(f"[ERROR] 숙소 추천 요청 처리 중 오류 발생: {e}")
        raise HTTPException(status_code=500, detail=str(e))
