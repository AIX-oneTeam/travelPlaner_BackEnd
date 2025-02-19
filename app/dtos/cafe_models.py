from pydantic import BaseModel, Field
from typing import List

class CafeData(BaseModel):
    main_location: str
    keywords: List[str]
    n_posting: int
    placeId: str
    kor_name: str
    address: str
    atmosphere: str 
    signature_menu: str
    main_features: str
    positive_reviews: str 
    negative_reviews: str
    url: str
    image_url: str
    map_url: str
    latitude: float
    longitude: float
    phone_number: str
    business_status: bool
    business_hours: str
    
class CafeList(BaseModel):
    spots: list[CafeData]    