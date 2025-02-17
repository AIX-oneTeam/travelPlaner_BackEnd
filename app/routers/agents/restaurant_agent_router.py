from fastapi import APIRouter, HTTPException, Query, Body, Depends
from app.repository.db import get_async_session
from sqlmodel.ext.asyncio.session import AsyncSession
from typing import Optional
from app.routers.agents.travel_all_schedule_agent_router import TravelPlanRequest
from app.services.agents.restaurant_agent_service import RestaurantAgentService

router = APIRouter()

restaurant_service = RestaurantAgentService()


@router.post("/restaurant")
async def get_restaurants(
    user_input: TravelPlanRequest = Body(...),
    prompt: Optional[str] = Query(None),
    session: AsyncSession = Depends(get_async_session),
):
    """
    맛집 추천 엔드포인트
    """
    try:
        # model_dump()를 사용하여 입력 데이터를 dict 형태로 변환
        # plan_id 확인 - 디버깅
        input_data = user_input.model_dump()

        # plan_id = input_data.get('plan_id')
        # print(f"[plan_id]: {plan_id}")
        print(f"✅ [input_data]: {input_data}")

        # prompt 값이 있을 경우, 딕셔너리에 추가 (user_input에는 직접 할당 불가)
        if prompt:
            input_data["prompt"] = prompt

        try:
            result = await restaurant_service.create_recommendation(input_data, prompt, session)
        except Exception as e:
            print(f"[ERROR] create_recommendation() 오류 발생: {e}")
            raise HTTPException(status_code=500, detail="추천 생성 중 오류 발생")

        print("restaurant_response:", result)

        return {
            "status": "success",
            "message": "맛집 리스트가 생성되었습니다.",
            "data": result,
        }

    except Exception as e:
        print(f"[ERROR] 요청 처리 중 오류 발생: {e}")
        raise HTTPException(status_code=500, detail=str(e))
