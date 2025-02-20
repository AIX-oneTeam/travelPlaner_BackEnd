from typing import Optional
from fastapi import APIRouter, HTTPException, Depends, Query, Body
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
    user_input: TravelPlanRequest = Body(...),
    prompt:Optional[str]= Query(None),
    session: AsyncSession = Depends(get_async_session),
    redis_client: Redis = Depends(get_redis),
    debug:Optional[bool] = False
    ):
    """
    카페 추천 엔드포인트
    """
    try:
        if str(debug).lower() == "true":
            return {
                "status": "success",
                "message": "카페 리스트가 생성되었습니다.",
                "data": {
                    "spots": DUMMY_CAFE_LIST }
            }
                    
        # model_dump()를 사용하여 입력 데이터를 dict 형태로 변환
        input_data = user_input.model_dump()
        # print(f"input_data : {input_data}")

        if prompt:
            input_data["prompt"] = prompt

        result = await cafe_service.create_recommendation_cafe(
            input_data=input_data, session=session, redis_client= redis_client
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
        
        
DUMMY_CAFE_LIST = [
    {
        "kor_name": "투드커피",
        "eng_name": "Tood Coffee",
        "description": "따뜻하고 아늑한 느낌의 예쁜 카페로, 감성 가득한 인테리어와 소품들이 조화롭게 어우러져 있습니다. 인기 메뉴로는 투드라떼와 햄스터궁둥이베이글이 있으며, 디저트와 커피의 조화가 좋고, 직원들이 친절하다는 리뷰가 많습니다.",
        "address": "대전광역시 서구 상보안길 105 투드커피",
        "url": "https://www.instagram.com/tood_coffee",
        "image_url": "https://search.pstatic.net/common/?autoRotate=true&type=w560_sharpen&src=https%3A%2F%2Fvideo-phinf.pstatic.net%2F20250111_250%2F1736557121161vDx7E_JPEG%2Fkxnlz68Q98_03.jpg",
        "map_url": "https://map.kakao.com/link/map/36.2764977,127.3478491",
        "latitude": 36.2764977,
        "longitude": 127.3478491,
        "spot_category": 3,
        "phone_number": "0507-1367-0712",
        "business_status": "true",
        "business_hours": "11시 30분에 영업 시작",
        "order": 1,
        "day_x": 1,
        "spot_time": "08:00"
    },
    {
        "kor_name": "일오이오",
        "eng_name": "1525",
        "description": "넓고 깨끗한 대형 카페로, 가족 단위 방문에 적합합니다. 커피와 다양한 디저트가 인기이며, 인테리어가 예쁘고 디저트가 다양하다는 긍정적인 리뷰가 많습니다.",
        "address": "대전광역시 서구 관저중로64번길 24 카페 일오이오",
        "url": "https://www.instagram.com/cafe.1525",
        "image_url": "https://search.pstatic.net/common/?autoRotate=true&type=w560_sharpen&src=https%3A%2F%2Fldb-phinf.pstatic.net%2F20250203_184%2F1738566854178tLBFI_JPEG%2FKakaoTalk_20250124_155253498_07_%25281%2529.jpg",
        "map_url": "https://map.kakao.com/link/map/36.2972096,127.3364105",
        "latitude": 36.2972096,
        "longitude": 127.3364105,
        "spot_category": 3,
        "phone_number": "042-822-5510",
        "business_status": "true",
        "business_hours": "23시 0분에 라스트오더",
        "order": 2,
        "day_x": 1,
        "spot_time": "12:00"
    },
    {
        "kor_name": "썬하우스",
        "eng_name": "Sun House",
        "description": "햇살이 잘 드는 아늑한 카페로, 감성적인 분위기가 특징입니다. 아메리카노와 공주밤 아이스크림이 시그니처 메뉴이며, 커피와 아이스크림의 조화가 좋고, 친절한 서비스에 대한 칭찬이 많습니다.",
        "address": "대전광역시 서구 탄방로 29 1층",
        "url": "http://www.instargram.com/ssunhouse_sh/",
        "image_url": "https://search.pstatic.net/common/?autoRotate=true&type=w560_sharpen&src=https%3A%2F%2Fldb-phinf.pstatic.net%2F20220916_261%2F1663310784554F7lRE_JPEG%2FF8BF0B0A-.jpg",
        "map_url": "https://map.kakao.com/link/map/36.3442938,127.390687",
        "latitude": 36.3442938,
        "longitude": 127.390687,
        "spot_category": 3,
        "phone_number": "0507-1313-0757",
        "business_status": "true",
        "business_hours": "23시 30분에 영업 종료",
        "order": 6,
        "day_x": 1,
        "spot_time": "18:00"
    },
    {
        "kor_name": "앤크",
        "eng_name": "Anc",
        "description": "깔끔하고 고급스러운 분위기로, 디저트와 커피를 즐기기 좋은 공간입니다. 밀푀유 프레지에와 생토노레가 시그니처 메뉴이며, 디저트의 맛과 비주얼에 대한 칭찬이 많습니다.",
        "address": "대전광역시 서구 청사서로 14 대성빌딩 1층",
        "url": "http://instagram.com/anc_dessert",
        "image_url": "https://search.pstatic.net/common/?autoRotate=true&type=w560_sharpen&src=https%3A%2F%2Fldb-phinf.pstatic.net%2F20250211_150%2F1739285551091D93AO_JPEG%2FIMG_2325.jpeg",
        "map_url": "https://map.kakao.com/link/map/36.3591247,127.3767811",
        "latitude": 36.3591247,
        "longitude": 127.3767811,
        "spot_category": 3,
        "phone_number": "0507-1318-3486",
        "business_status": "true",
        "business_hours": "20시 30분에 라스트오더",
        "order": 4,
        "day_x": 1,
        "spot_time": "18:00"
    }
]