from fastapi import APIRouter, HTTPException, Request
from app.services.agents.site_agent_service import SiteAgentService

router = APIRouter()


@router.post("/site")
async def get_site_plan(request: Request):
    """
    관광지 에이전트를 이용한 추천 엔드포인트.
    클라이언트는 URL 쿼리 파라미터로 prompt, 본문에는 TravelPlanRequest JSON 데이터를 전송합니다.
    예) /agents/site?prompt=추가 요청 내용
    """
    try:
        # URL 쿼리 파라미터에서 prompt 추출 (없으면 빈 문자열)
        prompt = request.query_params.get("prompt", "")
        # 본문에서 plan 데이터를 읽음
        plan_data = await request.json()
        if prompt:
            plan_data["prompt"] = prompt

        travel_service = SiteAgentService()
        result = await travel_service.create_tourist_plan(plan_data)
        return {
            "status": "success",
            "message": "관광지 추천 결과가 생성되었습니다.",
            "data": result,  # 이미 dict 또는 JSON 직렬화 가능한 형태라고 가정
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
