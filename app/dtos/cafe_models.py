from pydantic import BaseModel, Field
from typing import List

# 상세 정보를 위한 중첩 모델
class CafeDetail(BaseModel):
    atmosphere: str = Field(..., alias="분위기")
    signature_menu: str = Field(..., alias="시그니처 메뉴")
    main_features: str = Field(..., alias="주요 특징")
    positive_reviews: str = Field(..., alias="긍정 리뷰")
    negative_reviews: str = Field(..., alias="부정 리뷰")

class CafeData(BaseModel):
    main_location: str
    keywords: List[str]
    n_posting: int
    placeId: str
    kor_name: str
    address: str
    detail: CafeDetail
    url: str
    image_url: str
    latitude: float
    longitude: float
    phone_number: str
    business_status: bool
    business_hours: str
    
class CafeList(BaseModel):
    spots: list[CafeData]    