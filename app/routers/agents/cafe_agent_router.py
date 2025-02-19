from typing import Optional
from fastapi import APIRouter, HTTPException, Depends
from app.services.agents.cafe_agent_service import CafeAgentService
from app.routers.agents.travel_all_schedule_agent_router import TravelPlanRequest
from app.repository.redis_client import get_redis  # Redis 연결 함수
from app.repository.db import get_async_session
from sqlalchemy.ext.asyncio import AsyncSession
from redis.asyncio import Redis
router = APIRouter()

cafe_service = CafeAgentService()

@router.post("/cafe")
async def get_cafes(
    user_input: TravelPlanRequest,
    prompt:Optional[str],
    debug:Optional[bool]=False,
    redis_client: Redis = Depends(get_redis)
    ):
    """
    카페 정보를 가져오는 엔드포인트.
    - CrewAI 실행 후 일정(JSON) 반환.
    """
    if str(debug).lower() == "true":

        return {
            "status": "success",
            "message": "카페 리스트가 생성되었습니다.",
            "data": {
                "spots": [
                    {
                    "kor_name": "코랄라니",
                    "eng_name": "Coralani",
                    "description": "아름다운 바다 전망과 넓은 공간으로 편안한 분위기를 제공하는 카페로, 바다를 바라보며 커피를 즐길 수 있는 공간입니다. 시그니처 메뉴는 솔티코랄이며, 뷰가 멋지고 힐링하기 좋은 장소로 인기가 많습니다.",
                    "address": "부산광역시 기장군 기장읍 기장해안로 32",
                    "url": "https://www.instagram.com/cafecoralani/",
                    "image_url": "https://search.pstatic.net/common/?autoRotate=true&type=w560_sharpen&src=https%3A%2F%2Fldb-phinf.pstatic.net%2F20211003_132%2F16332718241265ECbW_JPEG%2FYwq7_LC_wSANgPqDQbYo3nvD.jpg",
                    "map_url": "https://map.kakao.com/link/map/35.1824438,129.2089009",
                    "latitude": 35.1824438,
                    "longitude": 129.2089009,
                    "spot_category": 3,
                    "phone_number": "051-721-6789",
                    "business_status": "true",
                    "business_hours": "21시 20분에 라스트오더",
                    "order": 1,
                    "day_x": 1,
                    "spot_time": "08:00"
                    },
                    {
                    "kor_name": "언더커피",
                    "eng_name": "Under Coffee",
                    "description": "힙하고 아늑한 분위기로 다양한 원두를 제공하며, 국가대표 바리스타가 운영하는 카페입니다. 시그니처 메뉴는 언더플랫과 로필즈라떼이며, 커피 맛이 뛰어나고 분위기가 좋다는 리뷰가 많습니다.",
                    "address": "부산광역시 수영구 광남로 52 1층",
                    "url": "https://smartstore.naver.com/undercoffee",
                    "image_url": "https://search.pstatic.net/common/?autoRotate=true&type=w560_sharpen&src=https%3A%2F%2Fldb-phinf.pstatic.net%2F20240112_183%2F1705049617249CGXO7_JPEG%2FKakaoTalk_20240112_175322143.jpg",
                    "map_url": "https://map.kakao.com/link/map/35.1470638,129.1123502",
                    "latitude": 35.1470638,
                    "longitude": 129.1123502,
                    "spot_category": 3,
                    "phone_number": "0507-1375-5712",
                    "business_status": "true",
                    "business_hours": "17시 30분에 라스트오더",
                    "order": 2,
                    "day_x": 1,
                    "spot_time": "12:00"
                    },
                    {
                    "kor_name": "리투커피바",
                    "eng_name": "Ritu Coffee Bar",
                    "description": "뷰가 좋은 카페로 편안한 분위기를 제공하며, 노밀가루 케익과 다양한 커피를 선택할 수 있습니다. 시그니처 메뉴는 바스크치즈케이크이며, 뷰가 좋고 디저트가 맛있다는 리뷰가 많습니다.",
                    "address": "부산광역시 기장군 일광읍 문오성길 396",
                    "url": "http://pf.kakao.com/_yKvJG",
                    "image_url": "https://search.pstatic.net/common/?autoRotate=true&type=w560_sharpen&src=https%3A%2F%2Fldb-phinf.pstatic.net%2F20250111_206%2F1736600906060InRrh_JPEG%2F1000002861.jpg", 
                    "map_url": "https://map.kakao.com/link/map/35.2942495,129.260775",
                    "latitude": 35.2942495,
                    "longitude": 129.260775,
                    "spot_category": 3,
                    "phone_number": "0507-1390-8611",
                    "business_status": "true",
                    "business_hours": "19시 30분에 라스트오더",
                    "order": 3,
                    "day_x": 1,
                    "spot_time": "18:00"
                    }
                ]}
        }
    try:
        result = await cafe_service.create_cafe_recommendation(user_input.model_dump(),
                                                          prompt = prompt,
                                                          redis_client= redis_client,
                                                        )     
        if not result:
            print("카페 결과값이 없습니다. ")

            raise HTTPException(
                status_code=404,
                detail={
                    "status": "error",
                    "message": "카페 검색 결과가 없습니다.",
                }
            )    

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
        