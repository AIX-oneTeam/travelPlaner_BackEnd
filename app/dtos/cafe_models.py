from pydantic import BaseModel
from typing import List

# 체크리스트 항목 단일 모델
class Cafe(BaseModel):
    placeId: str
    kor_name: str
    address: str
    latitude:float
    longitude: float
    phone_number: str         
    n_posting: int
    url: str 
    business_status: bool
    business_hour: str
    category: str
    description : str
    preference : str
    image_url: str
    map_url : str

# 여러 체크리스트 항목을 받을 때 사용
class CafeList(BaseModel):
    spots: List[Cafe]


