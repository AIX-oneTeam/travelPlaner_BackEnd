from fastapi import APIRouter, HTTPException, Request
import traceback
from app.services.agents.site_agent_service import TouristAgentService

router = APIRouter()


@router.post("/site")
async def get_site_plan(request: Request):
    """
    관광지 에이전트를 이용한 추천 엔드포인트.
    클라이언트는 URL 쿼리 파라미터로 prompt, 본문에는 JSON 데이터를 전송.
    """
    try:
        # URL 쿼리 파라미터로부터 prompt를 가져옵니다.
        prompt = request.query_params.get("prompt", "")
        plan_data = await request.json()

        # companion_count가 리스트가 아닌 경우 빈 리스트로 초기화 (예외 방지)
        if not isinstance(plan_data.get("companion_count", []), list):
            plan_data["companion_count"] = []

        # prompt가 존재하면 plan_data에 추가 (혹은 서비스에 별도로 전달)
        travel_service = TouristAgentService()
        result = await travel_service.create_tourist_plan(plan_data, prompt=prompt)

        return {
            "status": "success",
            "message": "관광지 추천 결과가 생성되었습니다.",
            "data": result,
        }
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))
