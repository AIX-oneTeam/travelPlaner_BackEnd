from fastapi import APIRouter, HTTPException
from app.services.agents.cafe_agent_service import CafeAgentService
from app.routers.agents.travel_all_schedule_agent_router import TravelPlanRequest
from datetime import datetime
router = APIRouter()

cafe_service = CafeAgentService()

@router.post("/cafe")
async def get_cafes(user_input: TravelPlanRequest):
    """
    카페 정보를 가져오는 엔드포인트.
    - CrewAI 실행 후 일정(JSON) 반환.
    """
    try:
        start_time = datetime.now()   

        result = await cafe_service.create_recommendation(user_input.model_dump())
        
        end_time = datetime.now()
        execution_time = (end_time - start_time).total_seconds()
        
        if not result:
            print("결과값이 없습니다. 실행 시간: {execution_time:.4f}초")

            raise HTTPException(
                status_code=404,
                detail={
                    "status": "error",
                    "message": "카페 검색 결과가 없습니다.",
                    "execution_time": execution_time
                }
            )    

        print(f"`create_recommendation()` 실행 시간: {execution_time:.4f}초")
        
        return {
            "status": "success",
            "message": "카페 리스트가 생성되었습니다.",
            "data": result,
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"카페 추천 처리 중 오류가 발생했습니다: {str(e)}"
        )
        