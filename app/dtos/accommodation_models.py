from typing import List, Optional
from pydantic import BaseModel


class AccommodationResponse(BaseModel):
    kor_name: str
    eng_name: Optional[str] = None
    description: str
    address: str
    latitude : str 
    longitude : str
    url: Optional[str] = None
    image_url: str
    map_url: str
    spot_category: int = 0
    phone_number: Optional[str] = None
    business_status: Optional[bool] = None
    business_hours: Optional[str] = None
    keywords: List[str]

    class Config:
        frozen = True


    